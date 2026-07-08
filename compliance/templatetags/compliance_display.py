"""Display-only Arabic helpers for the framework controls preview page.

IMPORTANT: These are DISPLAY-ONLY aids for the Arabic UI. They NEVER modify database data and are
NOT official Arabic text. Official Arabic content is used only when a real DB field
(control.title_ar / control.description_ar) is populated — see the template.
No AI / external API is used. Pure, deterministic string mappings.
"""
import re

from django import template

register = template.Library()

# Evidence type (Control.EVIDENCE_TYPE_CHOICES codes) -> Arabic display label.
_EVTYPE_AR = {
    'policy': 'وثيقة سياسة',
    'procedure': 'وثيقة إجراء',
    'screenshot': 'لقطة شاشة',
    'config': 'إعدادات/تهيئة النظام',
    'report': 'تقرير',
    'log': 'سجل',
    'interview': 'محضر مقابلة',
    'certificate': 'شهادة/رخصة',
    'other': 'أخرى',
    # extra synonyms that may appear in requirement templates.
    'evidence': 'مستند دليل',
    'risk_assessment': 'تقييم مخاطر',
    'contract': 'عقد/اتفاقية',
}

# Domain name (English) -> Arabic display label. Unknown names fall through unchanged.
_DOMAIN_AR = {
    'Cybersecurity Governance': 'حوكمة الأمن السيبراني',
    'Cybersecurity Defense': 'الدفاع السيبراني',
    'Cybersecurity Resilience': 'الصمود السيبراني',
    'Third Party Cybersecurity': 'الأمن السيبراني للأطراف الخارجية',
    'Third-Party Cybersecurity': 'الأمن السيبراني للأطراف الخارجية',
    'Cloud Cybersecurity': 'الأمن السيبراني السحابي',
    'Cloud Computing Cybersecurity': 'الأمن السيبراني للحوسبة السحابية',
}

# Per-evidence-type guidance ("ما المطلوب من الشركة؟"). Advisory — NOT a legal translation.
_REQUIREMENT_BY_EVTYPE = {
    'policy': 'جهّز وثيقة سياسة معتمدة توضّح هذا المتطلب، ويُفضّل أن تحتوي على المالك والنطاق وتاريخ الاعتماد وآلية المراجعة.',
    'procedure': 'جهّز وثيقة إجراء موثّقة تصف الخطوات والمسؤوليات اللازمة لتنفيذ هذا المتطلب.',
    'screenshot': 'احتفظ بلقطات شاشة أو أدلة مرئية تُظهر تطبيق هذا الضابط فعليًا على أنظمتك.',
    'config': 'احتفظ بإعدادات أو تهيئة النظام (تصدير الإعدادات) التي تُثبت الالتزام بهذا الضابط.',
    'report': 'جهّز تقريرًا (فحص أو تدقيق) يوثّق حالة الالتزام بهذا الضابط.',
    'log': 'احتفظ بسجلات النظام ذات الصلة التي تُثبت المراقبة والالتزام.',
    'interview': 'جهّز محضر مقابلة أو ما يوثّق مسؤوليات ووعي الفريق بهذا المتطلب.',
    'certificate': 'احتفظ بشهادة أو رخصة سارية تُثبت الالتزام بهذا المتطلب.',
}

# Per-domain guidance (takes precedence for these domains).
_REQUIREMENT_BY_DOMAIN = {
    'Cloud Cybersecurity': 'راجع إعدادات الخدمات السحابية، وحدّد المسؤوليات، واحتفظ بسياسات أو إعدادات أو سجلات تُثبت الالتزام.',
    'Cloud Computing Cybersecurity': 'راجع إعدادات الخدمات السحابية، وحدّد المسؤوليات، واحتفظ بسياسات أو إعدادات أو سجلات تُثبت الالتزام.',
    'Cybersecurity Governance': 'جهّز سياسة أو إجراء يوضّح المسؤوليات والاعتماد والحوكمة والمراجعة الدورية.',
}

_GENERIC_REQUIREMENT = ('جهّز الأدلة والوثائق التي تُثبت التزام منشأتك بهذا الضابط استعدادًا '
                        'لمراجعة المدقق. هذا وصف مساعد وليس نصًا رسميًا.')


@register.filter
def evtype_ar(code):
    """Arabic label for an evidence-type code; unknown codes return as-is."""
    return _EVTYPE_AR.get(str(code or '').strip().lower(), code)


@register.filter
def domain_ar(name):
    """Arabic label for a domain name; unknown names return unchanged (never breaks the page)."""
    if not name:
        return name
    return _DOMAIN_AR.get(str(name).strip(), name)


@register.filter
def company_requirement(control):
    """Advisory Arabic guidance ('ما المطلوب من الشركة؟') derived from the control's evidence type
    and domain. NOT a translation of the official text."""
    et = str(getattr(control, 'evidence_type', '') or '').strip().lower()
    dom = str(getattr(getattr(control, 'domain', None), 'name', '') or '').strip()
    if dom in _REQUIREMENT_BY_DOMAIN:
        return _REQUIREMENT_BY_DOMAIN[dom]
    return _REQUIREMENT_BY_EVTYPE.get(et, _GENERIC_REQUIREMENT)


# Targeted, safe fixes for common run-on artifacts in the official English text. DISPLAY ONLY —
# the database value is never modified.
_NORMALIZE_FIXES = [
    (re.compile(r'\bInadditionto\b'), 'In addition to'),
    (re.compile(r'\bsubcontrolsin\b'), 'subcontrols in'),
    (re.compile(r'\bthe(ECC|CSP|CST|CSC|CCC|OTCC|DCC)\b'), r'the \1'),
    (re.compile(r'\bcontrol(\d)'), r'control \1'),
    (re.compile(r'\bsubcontrol(\d)'), r'subcontrol \1'),
]


@register.filter
def normalize_en(text):
    """Improve readability of run-on English artifacts for DISPLAY ONLY. Never writes to the DB."""
    if not text:
        return text
    s = str(text)
    for pat, rep in _NORMALIZE_FIXES:
        s = pat.sub(rep, s)
    # Generic camelCase split (lowercase immediately followed by uppercase), e.g. "wordAnother".
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s)
    # Collapse any doubled spaces introduced above.
    s = re.sub(r'[ \t]{2,}', ' ', s)
    return s
