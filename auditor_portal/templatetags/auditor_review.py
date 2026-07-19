"""Display-only Arabic labels for the auditor review workspace.

UI/i18n helpers ONLY — no DB access, no logic. Map English enum values from
compliance.CompanyControl / Evidence / Assessment and the portal's own statuses to
Arabic for the internal review workspace. Unknown values pass through unchanged.
"""
from django import template

register = template.Library()

_CC_STATUS_AR = {
    'not_started': 'لم يبدأ',
    'in_progress': 'قيد التنفيذ',
    'evidence_uploaded': 'أدلة مرفوعة',
    'ai_reviewed': 'روجع آليًا',
    'compliant': 'ممتثل',
    'non_compliant': 'غير ممتثل',
    'partially_compliant': 'ممتثل جزئيًا',
    'not_applicable': 'لا ينطبق',
}

_EVIDENCE_STATUS_AR = {
    'uploaded': 'مرفوع',
    'processing': 'قيد الاستخراج',
    'ai_analyzing': 'تحليل استشاري جارٍ',
    'reviewed': 'روجع آليًا',
    'accepted': 'مقبول',
    'rejected': 'مرفوض',
    'needs_revision': 'يحتاج تعديل',
}

# AI advisory verdict — advisory only, never a final/official decision.
_AI_VERDICT_AR = {
    'compliant': 'مؤشر امتثال',
    'non_compliant': 'مؤشر عدم امتثال',
    'partially_compliant': 'امتثال جزئي',
    '': 'لم يُحلَّل',
}

_ASSESSMENT_STATUS_AR = {
    'draft': 'قيد الإعداد',
    'in_progress': 'قيد المراجعة',
    'ai_complete': 'اكتمل التحليل الاستشاري',
    'auditor_review': 'بانتظار مراجعة المدقق',
    'completed': 'مكتملة',
    'expired': 'منتهية',
}

_DOC_REQUEST_STATUS_AR = {
    'open': 'مفتوح',
    'pending': 'مفتوح',
    'responded': 'تم الرد',
    'under_review': 'قيد مراجعة المدقق',
    'closed': 'مغلق',
    'cancelled': 'ملغي',
    'submitted': 'تم الرفع',
    'accepted': 'مقبول',
    'rejected': 'مرفوض',
}

_VERDICT_STATUS_AR = {
    'not_reviewed': 'لم يراجع',
    'compliant': 'متوافق',
    'partially_compliant': 'متوافق جزئياً',
    'non_compliant': 'غير متوافق',
    'needs_more_evidence': 'يحتاج أدلة إضافية',
    'not_applicable': 'غير قابل للتطبيق',
}

_PRIORITY_AR = {'low': 'منخفضة', 'medium': 'متوسطة', 'high': 'عالية'}
_IMPACT_AR = {'low': 'منخفض', 'medium': 'متوسط', 'high': 'عالٍ', 'critical': 'حرج'}

_REPORT_VERDICT_AR = {
    'pass': 'جاهز مبدئيًا (مراجعة داخلية)',
    'conditional_pass': 'جاهز بشروط — يحتاج معالجة',
    'fail': 'غير كافٍ داخليًا',
}


def _ar(mapping, value):
    return mapping.get(str(value or '').strip().lower(), value or '—')


@register.filter
def cc_status_ar(value):
    return _ar(_CC_STATUS_AR, value)


@register.filter
def evidence_status_ar(value):
    return _ar(_EVIDENCE_STATUS_AR, value)


_PRIORITY_AR = {'critical': 'حرجة', 'high': 'عالية', 'medium': 'متوسطة', 'low': 'منخفضة'}
_EVIDENCE_TYPE_AR = {
    'policy': 'وثيقة سياسة', 'procedure': 'وثيقة إجراء', 'screenshot': 'لقطة شاشة',
    'config': 'تصدير إعدادات', 'report': 'تقرير تدقيق/فحص', 'log': 'سجل نظام',
    'interview': 'محضر مقابلة', 'certificate': 'شهادة/رخصة', 'other': 'أخرى',
}


@register.filter
def priority_ar(value):
    return _ar(_PRIORITY_AR, value)


@register.filter
def evidence_type_ar(value):
    return _ar(_EVIDENCE_TYPE_AR, value)


@register.filter
def ai_verdict_ar(value):
    return _AI_VERDICT_AR.get(str(value or '').strip().lower(), value)


@register.filter
def assessment_status_ar(value):
    return _ar(_ASSESSMENT_STATUS_AR, value)


@register.filter
def doc_request_status_ar(value):
    return _ar(_DOC_REQUEST_STATUS_AR, value)


@register.filter
def report_verdict_ar(value):
    return _ar(_REPORT_VERDICT_AR, value)


@register.filter
def verdict_status_ar(value):
    return _ar(_VERDICT_STATUS_AR, value)


@register.filter
def priority_ar(value):
    return _ar(_PRIORITY_AR, value)


@register.filter
def impact_ar(value):
    return _ar(_IMPACT_AR, value)
