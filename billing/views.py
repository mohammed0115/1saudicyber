"""Phase 8I-SUBSCRIPTION-A — company-facing billing/subscription pages.

Internal foundation only: shows subscription status + plans, starts a trial, and
selects a plan (which creates a pending manual payment). NO Moyasar checkout in
this phase. All views are company-portal guarded and tenant-scoped.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.shortcuts import render
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
    return render(request, 'billing/home.html', {
        'company': company,
        'subscription': sub,
        'plans': svc.active_plans(),
        'status_message': svc.get_subscription_status_message(company),
        'pending_payment': pending_payment,
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
    """POST-only: select a plan -> pending_payment subscription + pending payment."""
    company = request.user.company
    plan = svc.get_plan(request.POST.get('plan_code', ''))
    if plan is None:
        messages.error(request, 'الخطة غير موجودة · Plan not found.')
        return redirect('billing:home')
    try:
        svc.create_pending_subscription(company, plan, actor=request.user)
        messages.success(request, 'تم اختيار الخطة. الدفع الإلكتروني عبر Moyasar قادم لاحقًا. '
                                  '· Plan selected. Online payment via Moyasar is coming next.')
    except svc.SubscriptionError as e:
        messages.error(request, str(e))
    return redirect('billing:home')
