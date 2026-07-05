"""Phase 8I-SUBSCRIPTION-A — subscription lifecycle + feature/limit + guard services.

Internal foundation only. NO Moyasar API calls, NO checkout, NO webhooks, NO card
data, NO secrets. Reuses the existing single-per-company CompanySubscription
(OneToOne), so a company can never have two subscriptions. Every state change is
audited via core.AuditLog (never blocks the operation).
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import CompanySubscription, Plan, Payment
from .subscription_access import (get_company_subscription, ensure_company_subscription,
                                  company_has_active_subscription)

TRIAL_DAYS = 14
DEFAULT_PAID_DAYS = 30


class SubscriptionError(Exception):
    """Raised for an invalid subscription/payment operation."""


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def get_current_subscription(company):
    """The company's single subscription row (created inactive if missing)."""
    if company is None:
        return None
    return ensure_company_subscription(company)


def active_plans():
    return Plan.objects.filter(is_active=True).order_by('sort_order', 'price_amount')


def get_plan(code):
    return Plan.objects.filter(code=code, is_active=True).first()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@transaction.atomic
def start_trial(company, plan, actor=None):
    """Start a trial on the company's subscription (no duplicate rows possible)."""
    sub = ensure_company_subscription(company)
    now = timezone.now()
    sub.status = 'trial'
    sub.plan = plan
    sub.plan_name = plan.name if plan else (sub.plan_name or 'Trial')
    sub.starts_at = now
    sub.trial_ends_at = now + timedelta(days=TRIAL_DAYS)
    sub.ends_at = sub.trial_ends_at
    sub.provider = 'manual'
    if getattr(actor, 'is_authenticated', False):
        sub.created_by = sub.created_by or actor
        sub.updated_by = actor
    sub.save()
    _sub_audit(actor, company, 'subscription_trial_started', sub,
               extra={'plan': getattr(plan, 'code', '')})
    return sub


@transaction.atomic
def create_pending_subscription(company, plan, actor=None, provider='manual'):
    """Select a plan -> pending_payment subscription + a pending payment.

    provider is 'manual' (default; unchanged behaviour) or 'moyasar' (sandbox checkout).
    """
    if plan is None:
        raise SubscriptionError('الخطة غير موجودة · Plan not found.')
    provider = 'moyasar' if provider == 'moyasar' else 'manual'
    sub = ensure_company_subscription(company)
    sub.status = 'pending_payment'
    sub.plan = plan
    sub.plan_name = plan.name
    sub.provider = provider
    if getattr(actor, 'is_authenticated', False):
        sub.created_by = sub.created_by or actor
        sub.updated_by = actor
    sub.save()
    # BUG-1: reuse an existing pending MANUAL payment for this subscription instead of
    # creating a duplicate row on repeated plan selection. (Moyasar behaviour unchanged.)
    payment = None
    if provider == 'manual':
        payment = (Payment.objects.filter(company=company, subscription=sub,
                                          status='pending', provider='manual')
                   .order_by('-created_at').first())
        if payment is not None:
            payment.amount = plan.price_amount
            payment.currency = getattr(plan, 'currency', 'SAR')
            payment.reference = ('plan:%s' % plan.code)[:160]
            payment.save(update_fields=['amount', 'currency', 'reference', 'updated_at'])
    if payment is None:
        payment = create_manual_payment(sub, plan.price_amount, actor,
                                        reference='plan:%s' % plan.code, provider=provider)
    _sub_audit(actor, company, 'subscription_created', sub,
               extra={'plan': plan.code, 'payment_id': payment.id, 'status': 'pending_payment',
                      'provider': provider})
    return sub, payment


@transaction.atomic
def activate_subscription(subscription, actor=None, reason='', days=DEFAULT_PAID_DAYS):
    """Manually activate a subscription (staff/service). Idempotent-ish."""
    now = timezone.now()
    subscription.status = 'active'
    subscription.starts_at = subscription.starts_at or now
    subscription.activated_at = now
    subscription.ends_at = now + timedelta(days=days) if days else None
    if getattr(actor, 'is_authenticated', False):
        subscription.activated_by = actor
        subscription.updated_by = actor
    subscription.save()
    _sub_audit(actor, subscription.company, 'subscription_activated', subscription,
               extra={'reason': (reason or '')[:500], 'status': 'active'})
    return subscription


@transaction.atomic
def cancel_subscription(subscription, actor=None, reason=''):
    subscription.status = 'cancelled'
    subscription.cancelled_at = timezone.now()
    if getattr(actor, 'is_authenticated', False):
        subscription.updated_by = actor
    subscription.save()
    _sub_audit(actor, subscription.company, 'subscription_cancelled', subscription,
               extra={'reason': (reason or '')[:500], 'status': 'cancelled'})
    return subscription


@transaction.atomic
def expire_subscription(subscription, actor=None, reason=''):
    subscription.status = 'expired'
    if getattr(actor, 'is_authenticated', False):
        subscription.updated_by = actor
    subscription.save()
    _sub_audit(actor, subscription.company, 'subscription_expired', subscription,
               extra={'reason': (reason or '')[:500], 'status': 'expired'})
    return subscription


# ---------------------------------------------------------------------------
# Payments (manual now; Moyasar-ready fields, no API calls)
# ---------------------------------------------------------------------------
@transaction.atomic
def create_manual_payment(subscription, amount, actor=None, reference='', provider='manual'):
    company = subscription.company
    provider = 'moyasar' if provider == 'moyasar' else 'manual'
    payment = Payment.objects.create(
        company=company, subscription=subscription, provider=provider,
        amount=amount, currency=getattr(subscription.plan, 'currency', 'SAR'),
        status='pending', reference=(reference or '')[:160],
        created_by=actor if getattr(actor, 'is_authenticated', False) else None)
    _sub_audit(actor, company, 'manual_payment_created', subscription,
               extra={'payment_id': payment.id, 'amount': str(amount), 'provider': provider})
    return payment


@transaction.atomic
def cancel_pending_manual_payments(company, subscription, actor=None, reason=''):
    """Mark any pending MANUAL payment(s) for a subscription as cancelled (reject flow).

    Keeps the company's billing state unambiguous (no stale 'under review' banner) and
    never activates anything. Moyasar payments are left untouched.
    """
    qs = Payment.objects.filter(company=company, subscription=subscription,
                                status='pending', provider='manual')
    ids = list(qs.values_list('id', flat=True))
    n = qs.update(status='cancelled', updated_at=timezone.now())
    if n:
        _sub_audit(actor, company, 'manual_payment_cancelled', subscription,
                   extra={'payment_ids': ids, 'reason': (reason or '')[:500]})
    return n


@transaction.atomic
def mark_payment_paid(payment, actor=None, reason=''):
    payment.status = 'paid'
    payment.paid_at = timezone.now()
    payment.save(update_fields=['status', 'paid_at', 'updated_at'])
    # A paid manual payment activates a pending subscription.
    sub = payment.subscription
    if sub is not None and sub.status in ('pending_payment', 'past_due', 'inactive', 'expired'):
        activate_subscription(sub, actor=actor, reason='manual payment paid')
    _sub_audit(actor, payment.company, 'manual_payment_paid',
               sub, extra={'payment_id': payment.id, 'reason': (reason or '')[:500]})
    return payment


# ---------------------------------------------------------------------------
# Feature / limit resolution
# ---------------------------------------------------------------------------
def subscription_feature_enabled(company, feature_code):
    """True if the company's active subscription's plan enables the feature.

    Permissive default: an active subscription with no plan enables everything;
    no active subscription -> feature disabled.
    """
    if not company_has_active_subscription(company):
        return False
    sub = get_company_subscription(company)
    plan = getattr(sub, 'plan', None)
    if plan is None:
        return True
    if feature_code not in Plan.FEATURE_FLAGS:
        return False
    return bool(getattr(plan, feature_code, False))


def subscription_limit_value(company, limit_code):
    """Numeric limit from the plan (0 = unlimited / not set). 0 when no plan."""
    sub = get_company_subscription(company)
    plan = getattr(sub, 'plan', None) if sub else None
    if plan is None or limit_code not in Plan.LIMIT_FIELDS:
        return 0
    return int(getattr(plan, limit_code, 0) or 0)


# ---------------------------------------------------------------------------
# Access guard helpers (soft integration in this phase)
# ---------------------------------------------------------------------------
def can_access_feature(company, feature_code=None):
    """True if the company has an active/trial subscription (and the feature, if given)."""
    if not company_has_active_subscription(company):
        return False
    if feature_code is None:
        return True
    return subscription_feature_enabled(company, feature_code)


def require_active_subscription(company, feature_code=None):
    """Return None if access is allowed, else a safe bilingual message (soft gate)."""
    if can_access_feature(company, feature_code):
        return None
    return get_subscription_status_message(company)


def get_subscription_status_message(company):
    """A safe, bilingual status message for the company's subscription."""
    sub = get_company_subscription(company)
    if sub is None or sub.status == 'inactive':
        return 'لا يوجد اشتراك فعّال. ابدأ فترة تجريبية أو اختر خطة. · No active subscription — start a trial or choose a plan.'
    if sub.status == 'trial' and sub.is_active():
        return 'اشتراكك في فترة تجريبية. · Your subscription is in trial.'
    if sub.status == 'pending_payment':
        return 'بانتظار الدفع لتفعيل الاشتراك. · Awaiting payment to activate your subscription.'
    if sub.status == 'active' and sub.is_active():
        return 'اشتراكك فعّال. · Your subscription is active.'
    if sub.status == 'past_due':
        return 'اشتراكك متأخر السداد. · Your subscription is past due.'
    return 'اشتراكك غير فعّال حاليًا. · Your subscription is not currently active.'


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
def _sub_audit(actor, company, action, subscription=None, extra=None):
    try:
        from core.models import AuditLog
        meta = {
            'company_id': getattr(company, 'id', None),
            'subscription_id': getattr(subscription, 'id', None),
            'plan': getattr(getattr(subscription, 'plan', None), 'code', '') if subscription else '',
            'status': getattr(subscription, 'status', '') if subscription else '',
            'performed_by': getattr(actor, 'email', ''),
        }
        if extra:
            meta.update(extra)
        AuditLog.objects.create(
            user=actor if getattr(actor, 'is_authenticated', False) else None,
            action=action[:100], path='/billing/', metadata=meta)
    except Exception:
        pass
