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


_ENGAGEMENT_SCOPE_AR = {
    'reports_only': 'التقارير فقط', 'evidence_review': 'مراجعة الأدلة', 'full_review': 'مراجعة كاملة',
}


@register.filter
def engagement_scope_ar(value):
    """Auditor-assignment scope (code or English display) -> Arabic label."""
    return _ENGAGEMENT_SCOPE_AR.get(str(value or '').strip().lower().replace(' ', '_'), value)


# billing.access.FEATURE_FLAG short codes -> Arabic (plan feature labels). Display only.
_FEATURE_CODE_AR = {
    'evidence_upload': 'رفع الأدلة',
    'gap_analysis': 'تحليل الفجوات',
    'risk_engine': 'محرك المخاطر',
    'commercial_reports': 'التقارير التجارية',
    'pdf_export': 'تصدير PDF',
    'auditor_review': 'طلب مراجعة مدقق ذاتيًا',
}


@register.filter
def feature_code_ar(value):
    """Plan feature code (e.g. 'evidence_upload') -> Arabic label, keeping unknown as-is."""
    key = str(value or '').strip().lower()
    return _FEATURE_CODE_AR.get(key, value)


# F-AUDIT A1: normalized auditor-verdict status -> Arabic (for the cross-silo disagreement
# panel). Display only; mirrors the shared verdict vocabulary in compliance.verdict_resolver.
_VERDICT_NORM_AR = {
    'compliant': 'مطابق',
    'partially_compliant': 'مطابق جزئيًا',
    'non_compliant': 'غير مطابق',
    'not_applicable': 'لا ينطبق',
    'needs_more_evidence': 'يتطلب أدلة إضافية',
    'not_reviewed': 'لم يُراجَع',
}


@register.filter
def verdict_norm_ar(value):
    """Normalized verdict status -> Arabic label, keeping unknown/empty as-is."""
    return _VERDICT_NORM_AR.get(str(value or '').strip().lower(), value)


# billing.Payment.PROVIDER_CHOICES -> Arabic ('Moyasar' is a brand, kept as-is).
_PROVIDER_AR = {'manual': 'يدوي', 'moyasar': 'Moyasar'}


@register.filter
def provider_ar(value):
    """Payment provider (code or English display) -> Arabic, keeping the Moyasar brand."""
    key = str(value or '').strip().lower()
    return _PROVIDER_AR.get(key, value)


# core.Company.SECTOR_CHOICES -> Arabic (keyed by the raw code). Display only.
_SECTOR_AR = {
    'oil_gas': 'النفط والغاز', 'petrochemical': 'البتروكيماويات',
    'banking': 'البنوك والتمويل', 'telecom': 'الاتصالات', 'healthcare': 'الرعاية الصحية',
    'government': 'حكومي', 'defense': 'الدفاع', 'energy': 'الطاقة والمرافق',
    'manufacturing': 'التصنيع', 'technology': 'تقنية المعلومات',
    'logistics': 'اللوجستيات والنقل', 'construction': 'الإنشاءات', 'retail': 'التجزئة',
    'education': 'التعليم', 'other': 'أخرى',
}

# core.Company.SIZE_CHOICES -> Arabic (keyed by the raw code). Display only.
_SIZE_AR = {
    'micro': 'صغيرة جدًا (1-9 موظفين)',
    'small': 'صغيرة (10-49 موظفًا)',
    'medium': 'متوسطة (50-249 موظفًا)',
    'large': 'كبيرة (250-999 موظفًا)',
    'enterprise': 'مؤسسية (1000+ موظف)',
}


@register.filter
def sector_ar(value):
    """Company sector code -> Arabic label, keeping unknown values as-is."""
    return _SECTOR_AR.get(str(value or '').strip().lower(), value)


@register.filter
def size_ar(value):
    """Company size code -> Arabic label, keeping unknown values as-is."""
    return _SIZE_AR.get(str(value or '').strip().lower(), value)


# AuditorProfile.STATUS_CHOICES -> Arabic (keyed by code or English display). Display only.
_AUDITOR_STATUS_AR = {
    'pending_review': 'قيد المراجعة',
    'active': 'مفعّل',
    'suspended': 'موقوف مؤقتًا',
    'inactive': 'غير مفعّل',
}

# core.User.ROLE_CHOICES -> Arabic (keyed by code or English display). Display only.
_ROLE_AR = {
    'admin': 'مشرف المنصة',
    'company_admin': 'مدير الشركة',
    'compliance_officer': 'مسؤول الامتثال',
    'it_security': 'فريق تقنية/أمن المعلومات',
    'bu_manager': 'مدير وحدة أعمال',
    'executive': 'تنفيذي',
    'auditor': 'مدقق معتمد',
}


@register.filter
def auditor_status_ar(value):
    """Auditor account status (code or English display) -> Arabic label."""
    key = str(value or '').strip().lower().replace(' ', '_')
    return _AUDITOR_STATUS_AR.get(key, value)


@register.filter
def role_ar(value):
    """User role (code or English display) -> Arabic label, keeping unknown as-is."""
    key = str(value or '').strip().lower().replace(' ', '_').replace('/', '_')
    return _ROLE_AR.get(key, value)
