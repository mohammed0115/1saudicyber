"""Phase 8I-D — plan-based feature access + limit enforcement.

Deterministic, tenant-safe, no payment API, no secrets, no card data. Builds on the
existing subscription helpers (subscription_services / subscription_access) — it does
NOT duplicate subscription state logic.

Enforcement philosophy for the internal readiness tools (evidence/gap/risk/reports):
* A plan that explicitly DISABLES a feature flag, or a plan LIMIT that is reached,
  hard-blocks the action.
* "No active subscription" is a soft state for these internal tools — the access
  RESULT reports it as blocked (reason=no_subscription) for display/CRM, but the view
  enforcement treats it as non-blocking so companies keep seeing their own preliminary
  readiness (matching existing product behaviour). See ``blocks_view``.
"""
from django.urls import reverse

from . import subscription_services as svc
from .subscription_access import get_company_subscription, company_has_active_subscription

# Short feature code -> Plan flag field.
FEATURE_FLAG = {
    'evidence_upload': 'evidence_upload_enabled',
    'gap_analysis': 'gap_analysis_enabled',
    'risk_engine': 'risk_engine_enabled',
    'commercial_reports': 'commercial_reports_enabled',
    'pdf_export': 'pdf_export_enabled',
    'auditor_review': 'auditor_review_enabled',
}
# Short feature code -> Plan limit field (only features that meter usage).
FEATURE_LIMIT = {
    'evidence_upload': 'max_evidence_files',
    'pdf_export': 'max_pdf_exports',
}

_MESSAGES = {
    'no_subscription': ('لا يوجد اشتراك فعّال لهذه الميزة.',
                        'No active subscription for this feature.'),
    'feature_disabled': ('هذه الميزة غير متاحة في خطتك الحالية.',
                         'This feature is not included in your current plan.'),
    'limit_reached': ('وصلت إلى الحد المسموح في خطتك.',
                      'You have reached your plan limit.'),
    'allowed': ('', ''),
}


class FeatureAccessResult:
    """A safe, self-describing access decision (no secrets, no card data)."""

    def __init__(self, allowed, reason_code='allowed', feature_code='',
                 current_usage=None, limit=0, plan_code=''):
        self.allowed = bool(allowed)
        self.reason_code = reason_code
        self.feature_code = feature_code
        self.current_usage = current_usage
        self.limit = int(limit or 0)
        self.plan_code = plan_code or ''
        ar, en = _MESSAGES.get(reason_code, ('', ''))
        self.message_ar = ar
        self.message_en = en
        try:
            self.upgrade_url = reverse('billing:home')
        except Exception:
            self.upgrade_url = '/billing/'

    def __bool__(self):
        return self.allowed

    @property
    def blocks_view(self):
        """True only for hard plan restrictions (disabled flag / limit reached).

        A missing subscription does NOT hard-block the internal readiness tools.
        """
        return (not self.allowed) and self.reason_code in ('feature_disabled', 'limit_reached')

    def as_dict(self):
        return {
            'allowed': self.allowed, 'reason_code': self.reason_code,
            'feature_code': self.feature_code, 'current_usage': self.current_usage,
            'limit': self.limit, 'plan_code': self.plan_code,
            'message_ar': self.message_ar, 'message_en': self.message_en,
            'upgrade_url': self.upgrade_url,
        }


def _active_plan(company):
    """The plan attached to the company's ACTIVE subscription (or None)."""
    if not company_has_active_subscription(company):
        return None
    sub = get_company_subscription(company)
    return getattr(sub, 'plan', None) if sub else None


def _plan_code(company):
    sub = get_company_subscription(company)
    plan = getattr(sub, 'plan', None) if sub else None
    return getattr(plan, 'code', '') if plan else ''


def feature_usage(company, feature_code):
    """Current usage count for a metered feature, or None if not reliably trackable."""
    if company is None:
        return None
    try:
        if feature_code == 'evidence_upload':
            from compliance.models import EvidenceSubmission
            return EvidenceSubmission.objects.filter(company=company).count()
        if feature_code == 'pdf_export':
            from core.models import AuditLog
            return AuditLog.objects.filter(
                action='report_pdf_exported', metadata__company_id=company.id).count()
    except Exception:
        return None
    return None


def frameworks_usage(company):
    """Count of the company's approved framework scopes (for max_frameworks display)."""
    if company is None:
        return None
    try:
        from compliance.models import CompanyFrameworkScope
        return CompanyFrameworkScope.objects.filter(company=company, status='approved').count()
    except Exception:
        return None


def check_feature_access(company, feature_code, usage=None):
    """Return a FeatureAccessResult for the company + feature.

    Order: active subscription -> plan feature flag -> plan limit. A plan of None on an
    active subscription is permissive (all features enabled, no limits).
    """
    plan_code = _plan_code(company)
    if not company_has_active_subscription(company):
        return FeatureAccessResult(False, 'no_subscription', feature_code, plan_code=plan_code)

    plan = _active_plan(company)
    flag = FEATURE_FLAG.get(feature_code)
    if plan is not None and flag and not bool(getattr(plan, flag, False)):
        return FeatureAccessResult(False, 'feature_disabled', feature_code, plan_code=plan_code)

    limit_field = FEATURE_LIMIT.get(feature_code)
    if plan is not None and limit_field:
        limit = svc.subscription_limit_value(company, limit_field)
        if limit and limit > 0:
            used = usage if usage is not None else feature_usage(company, feature_code)
            if used is not None and used >= limit:
                return FeatureAccessResult(False, 'limit_reached', feature_code,
                                           current_usage=used, limit=limit, plan_code=plan_code)
            return FeatureAccessResult(True, 'allowed', feature_code,
                                       current_usage=used, limit=limit, plan_code=plan_code)
    return FeatureAccessResult(True, 'allowed', feature_code, plan_code=plan_code)


# ---------------------------------------------------------------------------
# View enforcement + audit
# ---------------------------------------------------------------------------
# Per-feature primary audit action for a blocked attempt.
_BLOCK_ACTION = {
    'evidence_upload': 'evidence_upload_blocked',
    'gap_analysis': 'gap_run_blocked',
    'risk_engine': 'risk_generation_blocked',
    'pdf_export': 'pdf_export_blocked',
    'commercial_reports': 'feature_access_blocked',
    'auditor_review': 'feature_access_blocked',
}


def audit_feature_block(actor, company, result, request=None):
    """Audit a blocked feature attempt (safe metadata only; never blocks the request)."""
    try:
        from core.models import AuditLog
        meta = {
            'company_id': getattr(company, 'id', None),
            'feature_code': result.feature_code,
            'reason_code': result.reason_code,
            'current_usage': result.current_usage,
            'limit': result.limit,
            'plan_code': result.plan_code,
            'performed_by': getattr(actor, 'email', ''),
        }
        path = getattr(request, 'path', '/billing/') if request is not None else '/billing/'
        AuditLog.objects.create(
            user=actor if getattr(actor, 'is_authenticated', False) else None,
            action=_BLOCK_ACTION.get(result.feature_code, 'feature_access_blocked'),
            path=path[:300], metadata=meta)
        if result.reason_code == 'limit_reached':
            AuditLog.objects.create(
                user=actor if getattr(actor, 'is_authenticated', False) else None,
                action='limit_exceeded', path=path[:300], metadata=meta)
    except Exception:
        pass


def enforce_feature(request, company, feature_code, usage=None):
    """Check + audit. Returns (result, blocked: bool). ``blocked`` is True only for hard
    plan restrictions; the caller then renders/redirects with a safe upgrade message."""
    result = check_feature_access(company, feature_code, usage=usage)
    blocked = result.blocks_view
    if blocked:
        audit_feature_block(getattr(request, 'user', None), company, result, request=request)
    return result, blocked


def plan_feature_summary(company):
    """Safe per-plan feature + limit + usage summary for billing/CRM (no secrets)."""
    sub = get_company_subscription(company)
    plan = getattr(sub, 'plan', None) if sub else None
    features = []
    for code, flag in FEATURE_FLAG.items():
        enabled = True if plan is None else bool(getattr(plan, flag, False))
        features.append({'code': code, 'enabled': enabled})
    ev_used = feature_usage(company, 'evidence_upload')
    pdf_used = feature_usage(company, 'pdf_export')
    fw_used = frameworks_usage(company)
    return {
        'plan_code': getattr(plan, 'code', '') if plan else '',
        'plan_name': getattr(plan, 'name', '') if plan else '',
        'has_active': company_has_active_subscription(company),
        'features': features,
        'evidence_used': ev_used,
        'evidence_limit': svc.subscription_limit_value(company, 'max_evidence_files'),
        'pdf_used': pdf_used,
        'pdf_limit': svc.subscription_limit_value(company, 'max_pdf_exports'),
        'frameworks_used': fw_used,
        'frameworks_limit': svc.subscription_limit_value(company, 'max_frameworks'),
    }
