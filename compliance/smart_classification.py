"""
Phase 6A — deterministic, advisory Smart Classification (read-only).

Produces an advisory "تصنيف أولي استشاري" from EXISTING company + intake data:
recommended frameworks (with official control counts), a risk level, the missing
inputs that would sharpen the result, and a next action.

Guarantees:
* Pure deterministic rules — no AI, no randomness, no external/network calls.
* Read-only — never writes, never creates CompanyControl / Evidence /
  FrameworkApplicabilityResult, never issues a final compliance decision.
* Counts come from the official control library (FrameworkVersion), preferring
  the live DB count and falling back to the authoritative official totals. The
  legacy 334-control set is intentionally never used.

It mirrors the signal semantics of compliance/framework_applicability.py so the
advisory summary stays consistent with the deterministic applicability engine,
without re-running or rewriting it.
"""
from dataclasses import dataclass, field

# Advisory status values for a framework recommendation.
REQUIRED = 'required'
RECOMMENDED = 'recommended'
OPTIONAL = 'optional'
NOT_INDICATED = 'not_indicated'

STATUS_AR = {
    REQUIRED: 'مطلوب',
    RECOMMENDED: 'موصى به',
    OPTIONAL: 'اختياري',
    NOT_INDICATED: 'غير مُشار إليه حاليًا',
}

RISK_AR = {'low': 'منخفض', 'medium': 'متوسط', 'high': 'مرتفع', 'unknown': 'غير محدد'}

# Canonical official frameworks (advisory). `expected` is the authoritative
# official control count; the live DB count is preferred when imported.
# Sum of expected counts = 417 (NOT the legacy 334).
OFFICIAL_FRAMEWORKS = [
    dict(code='NCA-ECC-2-2024',     ar='الضوابط الأساسية للأمن السيبراني (ECC 2:2024)', en='NCA ECC 2:2024',      expected=108),
    dict(code='NCA-CSCC-1-2019',    ar='ضوابط الأنظمة الحساسة (CSCC)',                   en='NCA CSCC',            expected=32),
    dict(code='NCA-CCC-2-2024',     ar='ضوابط الحوسبة السحابية (CCC 2:2024)',            en='NCA CCC 2:2024',      expected=55),
    dict(code='NCA-TCC-1-2021',     ar='ضوابط العمل عن بُعد (TCC)',                      en='NCA TCC',             expected=21),
    dict(code='NCA-OSMACC-1-2021',  ar='ضوابط حسابات التواصل الرسمية (OSMACC)',          en='NCA OSMACC',          expected=15),
    dict(code='ARAMCO-SACS-002',    ar='أرامكو SACS-002',                               en='Aramco SACS-002',     expected=92),
    dict(code='SABIC-CYBERTRUST-1-0', ar='سابك سايبر ترست (SABIC CyberTrust)',          en='SABIC CyberTrust',    expected=94),
]
OFFICIAL_TOTAL = sum(f['expected'] for f in OFFICIAL_FRAMEWORKS)  # == 417
_FW = {f['code']: f for f in OFFICIAL_FRAMEWORKS}

HIGH_RISK_SECTORS = {'oil_gas', 'petrochemical', 'energy', 'banking',
                     'government', 'defense', 'healthcare', 'telecom'}
MEDIUM_RISK_SECTORS = {'manufacturing', 'technology', 'logistics', 'education', 'construction'}


def official_control_count(version_code):
    """Live official-control count for a framework version, preferring the DB and
    falling back to the authoritative official total. Never returns legacy 334."""
    from compliance.models import Control
    expected = _FW.get(version_code, {}).get('expected', 0)
    n = Control.objects.filter(framework_version__code=version_code,
                               is_legacy_import=False).count()
    return n if n > 0 else expected


@dataclass
class ClassificationInput:
    sector: str = ''
    size: str = ''
    country: str = 'SA'
    has_cr_number: bool = False
    target_nca: bool = False
    target_aramco: bool = False
    target_sabic: bool = False
    has_intake_profile: bool = False
    # Intake signals (only meaningful when has_intake_profile is True).
    is_government_entity: bool = False
    is_critical_system_operator: bool = False
    uses_cloud_services: bool = False
    provides_cloud_services: bool = False
    handles_sensitive_data: bool = False
    handles_personal_data: bool = False
    has_ot_environment: bool = False
    has_remote_work: bool = False
    manages_official_social_media_accounts: bool = False
    works_with_aramco: bool = False
    works_with_sabic: bool = False

    @property
    def in_ksa(self):
        c = (self.country or '').strip().lower()
        return c in ('', 'sa', 'ksa', 'saudi arabia', 'المملكة العربية السعودية')


@dataclass
class FrameworkRecommendation:
    code: str
    name_ar: str
    name_en: str
    status: str
    reason_ar: str
    reason_en: str
    control_count: int
    confidence: int  # deterministic 0-100

    @property
    def status_ar(self):
        return STATUS_AR.get(self.status, self.status)

    @property
    def is_indicated(self):
        return self.status in (REQUIRED, RECOMMENDED, OPTIONAL)


@dataclass
class ClassificationResult:
    risk_level: str
    recommendations: list = field(default_factory=list)
    missing_inputs: list = field(default_factory=list)
    next_action: str = ''
    has_intake: bool = False
    overall_confidence: int = 0
    advisory_label: str = 'تصنيف أولي استشاري'
    risk_reason_ar: str = ''

    @property
    def risk_level_ar(self):
        return RISK_AR.get(self.risk_level, self.risk_level)

    @property
    def indicated(self):
        return [r for r in self.recommendations if r.is_indicated]

    @property
    def recommended_count(self):
        return len(self.indicated)

    @property
    def total_expected_controls(self):
        return sum(r.control_count for r in self.indicated)


def build_input(company) -> ClassificationInput:
    """Build a ClassificationInput from EXISTING company + intake data (read-only)."""
    from compliance.models import CompanyIntakeProfile
    p = CompanyIntakeProfile.objects.filter(company=company).first()
    ci = ClassificationInput(
        sector=getattr(company, 'sector', '') or '',
        size=getattr(company, 'size', '') or '',
        country=getattr(company, 'country', 'SA') or 'SA',
        has_cr_number=bool(getattr(company, 'cr_number', '')),
        target_nca=bool(getattr(company, 'target_nca', False)),
        target_aramco=bool(getattr(company, 'target_aramco', False)),
        target_sabic=bool(getattr(company, 'target_sabic', False)),
        has_intake_profile=p is not None,
    )
    if p is not None:
        for fld in ('is_government_entity', 'is_critical_system_operator', 'uses_cloud_services',
                    'provides_cloud_services', 'handles_sensitive_data', 'handles_personal_data',
                    'has_ot_environment', 'has_remote_work', 'manages_official_social_media_accounts',
                    'works_with_aramco', 'works_with_sabic'):
            setattr(ci, fld, bool(getattr(p, fld, False)))
    return ci


def _rec(code, status, reason_ar, reason_en, confidence):
    f = _FW[code]
    return FrameworkRecommendation(
        code=code, name_ar=f['ar'], name_en=f['en'], status=status,
        reason_ar=reason_ar, reason_en=reason_en,
        control_count=official_control_count(code), confidence=confidence)


def _classify_ecc(ci):
    if ci.has_intake_profile and any([ci.is_government_entity, ci.is_critical_system_operator,
                                       ci.uses_cloud_services, ci.provides_cloud_services,
                                       ci.has_ot_environment, ci.handles_sensitive_data,
                                       ci.handles_personal_data, ci.has_remote_work]):
        return _rec('NCA-ECC-2-2024', REQUIRED,
                    'وجود نطاق سيبراني واضح وفق إجابات التصنيف.',
                    'A clear cybersecurity scope per intake answers.', 92)
    if ci.target_nca:
        return _rec('NCA-ECC-2-2024', REQUIRED,
                    'تم اختيار جاهزية الهيئة الوطنية (NCA).',
                    'NCA readiness goal was selected.', 88)
    if ci.in_ksa:
        return _rec('NCA-ECC-2-2024', REQUIRED,
                    'نشاط داخل المملكة — الضوابط الأساسية مطلوبة كحد أدنى.',
                    'Operating in Saudi Arabia — ECC is the baseline minimum.', 80)
    return _rec('NCA-ECC-2-2024', RECOMMENDED,
                'يُوصى بالضوابط الأساسية كأساس عام للأمن السيبراني.',
                'ECC is recommended as a general cybersecurity baseline.', 60)


def _classify_cscc(ci):
    # UAT-A: CSCC is proposed ONLY when the company explicitly indicates it operates/hosts
    # critical or national-critical systems. Sector alone must NEVER pull CSCC into scope.
    if ci.has_intake_profile and ci.is_critical_system_operator:
        return _rec('NCA-CSCC-1-2019', RECOMMENDED,
                    'تم اقتراح هذا الإطار لأن الشركة تشغّل أو تستضيف أنظمة حساسة أو بنية وطنية حرجة.',
                    'Operates critical systems per intake.', 90)
    return _rec('NCA-CSCC-1-2019', NOT_INDICATED,
                'لا يوجد ما يشير إلى تشغيل أنظمة حساسة بناءً على إجابات التصنيف.',
                'No critical-systems operation indicated by available data.', 70)


def _classify_ccc(ci):
    if ci.has_intake_profile and (ci.uses_cloud_services or ci.provides_cloud_services):
        return _rec('NCA-CCC-2-2024', RECOMMENDED,
                    'استخدام أو تقديم خدمات سحابية وفق إجابات التصنيف.',
                    'Uses or provides cloud services per intake.', 90)
    if ci.sector == 'technology':
        return _rec('NCA-CCC-2-2024', OPTIONAL,
                    'قطاع تقني — قد تنطبق ضوابط الحوسبة السحابية (يتطلب تأكيد).',
                    'Technology sector — CCC may apply (needs confirmation).', 50)
    return _rec('NCA-CCC-2-2024', NOT_INDICATED,
                'لا يوجد استخدام أو تقديم خدمات سحابية مُشار إليه بناءً على البيانات المتاحة.',
                'No cloud usage/provision indicated by available data.', 70)


def _classify_tcc(ci):
    if ci.has_intake_profile and ci.has_remote_work:
        return _rec('NCA-TCC-1-2021', RECOMMENDED,
                    'اعتماد نموذج العمل عن بُعد وفق إجابات التصنيف.',
                    'Telework is a meaningful operating model per intake.', 90)
    return _rec('NCA-TCC-1-2021', NOT_INDICATED,
                'لا يوجد ما يشير إلى اعتماد العمل عن بُعد بناءً على البيانات المتاحة.',
                'No telework operating model indicated by available data.', 70)


def _classify_osmacc(ci):
    if ci.has_intake_profile and ci.manages_official_social_media_accounts:
        return _rec('NCA-OSMACC-1-2021', RECOMMENDED,
                    'إدارة حسابات تواصل اجتماعي رسمية وفق إجابات التصنيف.',
                    'Manages official social media accounts per intake.', 90)
    return _rec('NCA-OSMACC-1-2021', NOT_INDICATED,
                'لا يوجد ما يشير إلى إدارة حسابات تواصل رسمية بناءً على البيانات المتاحة.',
                'No official social media account management indicated.', 70)


def _classify_aramco(ci):
    # UAT-B: supplier frameworks depend ONLY on the explicit supplier signal (checkbox) or the
    # explicit Aramco readiness goal — never on sector heuristics or a stale supplier dropdown.
    if ci.has_intake_profile and ci.works_with_aramco:
        return _rec('ARAMCO-SACS-002', REQUIRED,
                    'تم اقتراح هذا الإطار لأن الشركة اختارت التعامل مع أرامكو السعودية.',
                    'Works with Saudi Aramco per intake.', 90)
    if ci.target_aramco:
        return _rec('ARAMCO-SACS-002', REQUIRED,
                    'تم اقتراح هذا الإطار لأن الشركة اختارت جاهزية أرامكو (SACS-002).',
                    'Aramco (SACS-002) readiness goal was selected.', 80)
    return _rec('ARAMCO-SACS-002', NOT_INDICATED,
                'لا توجد علاقة مع أرامكو مُشار إليها بناءً على إجابات التصنيف.',
                'No Aramco relationship indicated by available data.', 70)


def _classify_sabic(ci):
    if ci.has_intake_profile and ci.works_with_sabic:
        return _rec('SABIC-CYBERTRUST-1-0', REQUIRED,
                    'تم اقتراح هذا الإطار لأن الشركة اختارت التعامل مع سابك.',
                    'Works with SABIC per intake.', 90)
    if ci.target_sabic:
        return _rec('SABIC-CYBERTRUST-1-0', REQUIRED,
                    'تم اقتراح هذا الإطار لأن الشركة اختارت جاهزية سابك (SABIC CyberTrust).',
                    'SABIC (CyberTrust) readiness goal was selected.', 80)
    return _rec('SABIC-CYBERTRUST-1-0', NOT_INDICATED,
                'لا توجد علاقة مع سابك مُشار إليها بناءً على إجابات التصنيف.',
                'No SABIC relationship indicated by available data.', 70)


_CLASSIFIERS = [_classify_ecc, _classify_cscc, _classify_ccc, _classify_tcc,
                _classify_osmacc, _classify_aramco, _classify_sabic]


def _risk_level(ci):
    if not ci.sector:
        return 'unknown'
    if (ci.sector in HIGH_RISK_SECTORS or
            (ci.has_intake_profile and (ci.is_critical_system_operator or ci.has_ot_environment))):
        return 'high'
    if (ci.sector in MEDIUM_RISK_SECTORS or ci.size in ('large', 'enterprise') or
            ci.target_aramco or ci.target_sabic or
            (ci.has_intake_profile and (ci.handles_sensitive_data or ci.handles_personal_data
                                        or ci.works_with_aramco or ci.works_with_sabic))):
        return 'medium'
    return 'low'


def _risk_reason(ci):
    """UAT-8: an Arabic explanation of the risk level, built from the ACTUAL selected signals
    (never a generic message that could contradict the intake answers)."""
    drivers = []
    if ci.sector in HIGH_RISK_SECTORS:
        drivers.append('نشاط في قطاع حيوي')
    if ci.has_intake_profile:
        if ci.is_critical_system_operator:
            drivers.append('تشغيل أنظمة حساسة/بنية وطنية حرجة')
        if ci.has_ot_environment:
            drivers.append('وجود بيئة تقنية تشغيلية (OT)')
        if ci.uses_cloud_services or ci.provides_cloud_services:
            drivers.append('استخدام أو تقديم خدمات سحابية')
        if ci.has_remote_work:
            drivers.append('اعتماد العمل عن بُعد')
        if ci.works_with_aramco:
            drivers.append('التعامل مع أرامكو')
        if ci.works_with_sabic:
            drivers.append('التعامل مع سابك')
        if ci.handles_sensitive_data or ci.handles_personal_data:
            drivers.append('التعامل مع بيانات حساسة/شخصية')
    if ci.size in ('large', 'enterprise'):
        drivers.append('حجم المنشأة كبير')
    level = RISK_AR.get(_risk_level(ci), _risk_level(ci))
    if not ci.sector:
        return 'يتعذّر تحديد مستوى المخاطر بدقة قبل تحديد قطاع الشركة وإكمال ملف التصنيف.'
    if not drivers:
        return f'تم تصنيف مستوى المخاطر كـ«{level}» بناءً على القطاع وحجم النشاط وفق إجابات التصنيف.'
    return f'تم تصنيف مستوى المخاطر كـ«{level}» بسبب: ' + '، '.join(drivers) + ' (حسب إجابات التصنيف).'


def _missing_inputs(ci):
    missing = []
    if not ci.has_intake_profile:
        missing.append('أكمل ملف التصنيف التفصيلي (الأنظمة الحساسة، الخدمات السحابية، العمل عن بُعد، '
                       'حسابات التواصل الرسمية، علاقات أرامكو/سابك) لتدقيق التوصيات.')
    if not ci.sector:
        missing.append('حدّد قطاع الشركة.')
    if not ci.size:
        missing.append('حدّد حجم الشركة.')
    if not ci.has_cr_number:
        missing.append('أضف رقم السجل التجاري (CR).')
    return missing


def classify_company(company) -> ClassificationResult:
    """Deterministic advisory classification for a single company (read-only)."""
    ci = build_input(company)
    recs = [clf(ci) for clf in _CLASSIFIERS]
    missing = _missing_inputs(ci)

    indicated = [r for r in recs if r.is_indicated]
    if indicated:
        base = sum(r.confidence for r in indicated) // len(indicated)
    else:
        base = 50
    # Incomplete profile/data lowers confidence in the overall picture.
    if not ci.has_intake_profile:
        base = min(base, 60)
    overall = max(0, min(100, base - 5 * len(missing) if missing else base))

    if not ci.has_intake_profile:
        next_action = 'أكمل ملف التصنيف لتدقيق الأطر المقترحة قبل اعتماد النطاق.'
    else:
        next_action = 'راجع الأطر المقترحة ثم اعتمد النطاق الرسمي مع المختص.'

    return ClassificationResult(
        risk_level=_risk_level(ci),
        recommendations=recs,
        missing_inputs=missing,
        next_action=next_action,
        has_intake=ci.has_intake_profile,
        overall_confidence=overall,
        risk_reason_ar=_risk_reason(ci),
    )
