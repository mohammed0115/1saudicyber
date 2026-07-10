"""Display-only Arabic mappings for the Get Solution CRM company-detail page.

UI/i18n helpers ONLY. These filters DO NOT touch the database, models, or any
service — they map English enum *display* labels (Subscription/Payment status,
plan names) to Arabic for the internal platform-admin console. They are not
official translations and never change stored values. Unknown inputs (already
Arabic, technical framework codes, etc.) pass through unchanged.
"""
from django import template

register = template.Library()

# billing.Subscription.STATUS_CHOICES -> Arabic (keyed by the raw status code;
# also matched against the English display label, normalized).
_SUB_STATUS_AR = {
    'inactive': 'غير مفعّل',
    'trial': 'تجريبي',
    'pending_payment': 'بانتظار الدفع',
    'active': 'نشط',
    'expired': 'منتهٍ',
    'cancelled': 'ملغى',
}

# billing.Payment.STATUS_CHOICES -> Arabic.
_PAY_STATUS_AR = {
    'pending': 'بانتظار التأكيد',
    'paid': 'مؤكدة',
    'failed': 'فشل',
    'cancelled': 'ملغاة',
    'refunded': 'مُرجعة',
}

# Common plan names -> Arabic (the plan CODE stays internal; this is display only).
_PLAN_NAME_AR = {
    'basic': 'أساسية',
    'trial': 'تجريبية',
    'standard': 'قياسية',
    'professional': 'احترافية',
    'pro': 'احترافية',
    'enterprise': 'مؤسسية',
}


@register.filter
def sub_status_ar(value):
    """Subscription status (code or English display) -> Arabic label."""
    key = str(value or '').strip().lower().replace(' ', '_')
    return _SUB_STATUS_AR.get(key, value)


@register.filter
def pay_status_ar(value):
    """Payment status (code or English display) -> Arabic label."""
    key = str(value or '').strip().lower()
    return _PAY_STATUS_AR.get(key, value)


@register.filter
def plan_name_ar(value):
    """Plan name (e.g. 'Basic') -> Arabic label, keeping unknown names as-is."""
    key = str(value or '').strip().lower()
    return _PLAN_NAME_AR.get(key, value)


# CompanyCRMProfile.CRM_STATUS_CHOICES -> Arabic (mirrors crm_services.CRM_STATUS_AR
# so the dropdown/badge match the Arabic activity-log wording). Display only.
_CRM_STATUS_AR = {
    'new': 'جديدة',
    'onboarding': 'تهيئة',
    'active': 'نشطة',
    'needs_follow_up': 'تحتاج متابعة',
    'blocked': 'محظورة',
    'inactive': 'غير نشطة',
}


@register.filter
def crm_status_ar(value):
    """CRM follow-up status (code or English display) -> Arabic label."""
    key = str(value or '').strip().lower().replace(' ', '_').replace('-', '_')
    return _CRM_STATUS_AR.get(key, value)


# core.Company.STATUS_CHOICES -> Arabic (internal compliance lifecycle). Display only.
_COMPANY_STATUS_AR = {
    'registered': 'مسجلة',
    'classified': 'مصنّفة',
    'in_assessment': 'قيد التقييم',
    'audit_ready': 'جاهزة للتدقيق',
    'certified': 'معتمدة',
    'expired': 'منتهية الشهادة',
    'certificate_expired': 'منتهية الشهادة',
}


@register.filter
def company_status_ar(value):
    """Company lifecycle status (code or English display) -> Arabic label."""
    key = str(value or '').strip().lower().replace(' ', '_')
    return _COMPANY_STATUS_AR.get(key, value)


# AuditorAssignment.STATUS_CHOICES -> Arabic (company↔auditor engagement). Display only.
_ENGAGEMENT_STATUS_AR = {
    'none': 'لا يوجد',
    'requested': 'بانتظار الموافقة',
    'accepted': 'مقبول / مُسند',
    'rejected': 'مرفوض',
    'cancelled': 'ملغى',
    'completed': 'مكتمل',
}


@register.filter
def engagement_status_ar(value):
    """Auditor-assignment status (code or English display) -> Arabic label."""
    key = str(value or '').strip().lower()
    return _ENGAGEMENT_STATUS_AR.get(key, value)


# billing.access.FEATURE_FLAG short codes -> Arabic (plan feature labels). Display only.
_FEATURE_CODE_AR = {
    'evidence_upload': 'رفع الأدلة',
    'gap_analysis': 'تحليل الفجوات',
    'risk_engine': 'محرك المخاطر',
    'commercial_reports': 'التقارير التجارية',
    'pdf_export': 'تصدير PDF',
    'auditor_review': 'مراجعة المدقق',
}


@register.filter
def feature_code_ar(value):
    """Plan feature code (e.g. 'evidence_upload') -> Arabic label, keeping unknown as-is."""
    key = str(value or '').strip().lower()
    return _FEATURE_CODE_AR.get(key, value)


# billing.Payment.PROVIDER_CHOICES -> Arabic ('Moyasar' is a brand, kept as-is).
_PROVIDER_AR = {'manual': 'يدوي', 'moyasar': 'Moyasar'}


@register.filter
def provider_ar(value):
    """Payment provider (code or English display) -> Arabic, keeping the Moyasar brand."""
    key = str(value or '').strip().lower()
    return _PROVIDER_AR.get(key, value)
