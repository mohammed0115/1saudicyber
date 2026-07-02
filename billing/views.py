"""Phase 8I-SUBSCRIPTION-A — company-facing billing/subscription pages.

Internal foundation only: shows subscription status + plans, starts a trial, and
selects a plan (which creates a pending manual payment). NO Moyasar checkout in
this phase. All views are company-portal guarded and tenant-scoped.
"""
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.roles import company_portal_required
from . import subscription_services as svc


@login_required
@company_portal_required
def billing_home(request):
    """Current subscription status + available plans + pending payment."""
    company = request.user.company
    sub = svc.get_current_subscription(company)
    pending_payment = company.payments.filter(status='pending').order_by('-created_at').first()
    # A recent failed/cancelled Moyasar payment (only when nothing is pending/active).
    failed_payment = None
    if pending_payment is None and (sub is None or sub.status != 'active'):
        failed_payment = company.payments.filter(
            provider='moyasar', status__in=('failed', 'cancelled')).order_by('-created_at').first()
    from .access import plan_feature_summary
    return render(request, 'billing/home.html', {
        'company': company,
        'subscription': sub,
        'plans': svc.active_plans(),
        'status_message': svc.get_subscription_status_message(company),
        'pending_payment': pending_payment,
        'failed_payment': failed_payment,
        'feature_summary': plan_feature_summary(company),
        'can_start_trial': sub is None or sub.status in ('inactive', 'expired', 'cancelled'),
    })


@login_required
@company_portal_required
@require_http_methods(["POST"])
def start_trial(request):
    """POST-only: start a trial on the company's subscription."""
    company = request.user.company
    plan = svc.get_plan(request.POST.get('plan_code') or 'trial') or svc.get_plan('trial')
    svc.start_trial(company, plan, actor=request.user)
    messages.success(request, 'تم بدء الفترة التجريبية · Trial started.')
    return redirect('billing:home')


@login_required
@company_portal_required
@require_http_methods(["POST"])
def select_plan(request):
    """POST-only: select a plan -> pending_payment subscription + pending payment.

    When PAYMENT_PROVIDER=moyasar, the payment is created as a Moyasar payment and
    the user is sent to the sandbox checkout page; otherwise manual behaviour stays.
    """
    from . import moyasar
    company = request.user.company
    plan = svc.get_plan(request.POST.get('plan_code', ''))
    if plan is None:
        messages.error(request, 'الخطة غير موجودة · Plan not found.')
        return redirect('billing:home')
    provider = 'moyasar' if moyasar.is_moyasar_provider() else 'manual'
    try:
        sub, payment = svc.create_pending_subscription(company, plan, actor=request.user,
                                                       provider=provider)
    except svc.SubscriptionError as e:
        messages.error(request, str(e))
        return redirect('billing:home')
    if provider == 'moyasar':
        return redirect('billing:checkout', payment_id=payment.id)
    messages.success(request, 'تم اختيار الخطة. الدفع اليدوي قيد الانتظار. '
                              '· Plan selected. Manual payment is pending.')
    return redirect('billing:home')


@login_required
@company_portal_required
def checkout(request, payment_id):
    """Moyasar sandbox checkout page for one PENDING Moyasar payment (own company only)."""
    from . import moyasar
    from .models import Payment
    company = request.user.company
    payment = Payment.objects.filter(id=payment_id, company=company).select_related(
        'subscription', 'subscription__plan').first()
    if payment is None:
        messages.error(request, 'الدفعة غير موجودة أو لا تخصّ شركتك · Payment not found.')
        return redirect('billing:home')
    sub = payment.subscription
    # Only a pending Moyasar payment on a pending_payment subscription is checkout-able.
    if not (payment.provider == 'moyasar' and payment.status == 'pending'
            and sub is not None and sub.status == 'pending_payment'):
        messages.info(request, 'لا حاجة للدفع لهذه الدفعة حاليًا · This payment is not awaiting checkout.')
        return redirect('billing:home')

    configured = moyasar.is_configured()
    if configured:
        _audit(request.user, company, 'moyasar_checkout_started', payment)
    return render(request, 'billing/checkout.html', {
        'company': company, 'payment': payment, 'subscription': sub, 'plan': sub.plan,
        'configured': configured,
        'publishable_key': moyasar.publishable_key_for_template(),   # sandbox pk_test_ only
        'moyasar_mode': moyasar.moyasar_mode(),
        'callback_url': moyasar.build_callback_url(request, payment),
        'metadata': moyasar.checkout_metadata(payment),
        'amount_halalas': int(payment.amount * 100),                 # Moyasar uses smallest unit
        'moyasar_js': moyasar.MOYASAR_JS, 'moyasar_css': moyasar.MOYASAR_CSS,
    })


@login_required
@company_portal_required
def moyasar_callback(request):
    """Return route after Moyasar (sandbox). Records the result but NEVER activates.

    Tenant-scoped by request.user.company and by the internal payment id (ipid) we
    put on the callback URL, so a forged callback can never affect another company
    and can never activate a subscription (verification is Phase 8I-C).
    """
    from .models import Payment
    company = request.user.company
    ipid = request.GET.get('ipid', '')
    provider_payment_id = (request.GET.get('id', '') or '')[:128]
    status = (request.GET.get('status', '') or '')[:40]

    payment = Payment.objects.filter(id=ipid, company=company, provider='moyasar').first() \
        if str(ipid).isdigit() else None
    if payment is None:
        messages.info(request, 'تعذّر مطابقة نتيجة الدفع. عد إلى صفحة الاشتراك. '
                               '· Could not match the payment result. Please return to billing.')
        _audit(request.user, company, 'moyasar_callback_failed', None,
               extra={'reason': 'no_match', 'status': status})
        return redirect('billing:home')

    # Store the provider result (id/status) WITHOUT activating anything.
    if provider_payment_id and not payment.provider_payment_id:
        payment.provider_payment_id = provider_payment_id
    meta = dict(payment.provider_metadata or {})
    meta['callback_status'] = status
    payment.provider_metadata = meta
    if status in ('failed', 'cancelled') and payment.status == 'pending':
        payment.status = 'failed' if status == 'failed' else 'cancelled'
    payment.save(update_fields=['provider_payment_id', 'provider_metadata', 'status', 'updated_at'])

    _audit(request.user, company, 'moyasar_callback_received', payment,
           extra={'provider_payment_id': provider_payment_id, 'callback_status': status})
    if status in ('failed', 'cancelled'):
        messages.warning(request, 'لم تكتمل عملية الدفع · The payment did not complete.')
    else:
        messages.info(request, 'تم استلام نتيجة الدفع، وسيتم تأكيد الاشتراك بعد التحقق من الدفع. '
                               '· Payment result received. Subscription will be activated after verification.')
    return redirect('billing:home')


@csrf_exempt
@require_http_methods(["POST"])
def moyasar_webhook(request):
    """External Moyasar webhook (Phase 8I-C). CSRF-exempt but protected by verification.

    Activation happens ONLY inside process_moyasar_webhook after a server-side Fetch
    Payment confirms the payment. This view just parses the body safely and never
    leaks a stack trace, path, or secret.
    """
    from . import verification
    try:
        payload = json.loads((request.body or b'').decode('utf-8') or '{}')
    except Exception:
        verification._audit(None, None, 'moyasar_webhook_invalid', None, 'webhook', '',
                            extra={'reason': 'malformed_json'})
        return JsonResponse({'ok': False, 'error': 'invalid_payload'}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({'ok': False, 'error': 'invalid_payload'}, status=400)
    try:
        result = verification.process_moyasar_webhook(payload, headers=request.headers)
    except Exception:
        # Absolute backstop — never 500 to an external caller, never leak internals.
        return JsonResponse({'ok': False, 'error': 'processing_error'}, status=200)
    return JsonResponse({'ok': bool(result.get('ok', True)), 'status': result.get('action', 'none')},
                        status=int(result.get('http_status', 200)))


def _audit(actor, company, action, payment, extra=None):
    """Audit a Moyasar checkout/callback event (no card data, no secrets; never blocks)."""
    try:
        from core.models import AuditLog
        meta = {
            'company_id': getattr(company, 'id', None),
            'payment_id': getattr(payment, 'id', None),
            'subscription_id': getattr(payment, 'subscription_id', None) if payment else None,
            'performed_by': getattr(actor, 'email', ''),
        }
        if extra:
            meta.update(extra)
        AuditLog.objects.create(
            user=actor if getattr(actor, 'is_authenticated', False) else None,
            action=action[:100], path='/billing/', metadata=meta)
    except Exception:
        pass
