"""
Phase 6B — deterministic, advisory Applicability Engine (read-only preview).

Takes a company's profile/intake + Phase 6A classification and produces an
advisory preview of which official controls *appear to apply* to the company's
scope. It answers "is this control in scope?" — NOT "is the company compliant?".

Guarantees:
* Pure deterministic rules — no AI, no randomness, no external/network calls.
* Read-only — never writes, never creates CompanyControl / ControlApplicabilityResult
  / Assessment rows. It is a preview only.
* Counts come from the official control library (FrameworkVersion), preferring the
  live DB count and falling back to the authoritative totals (417, never 334).
* It never produces a compliance status (C/PC/NC, Compliance/Noncompliance) and
  never issues a final/auditor verdict — those belong to later phases.

Distinct from the persisted pipeline (framework_applicability.py / framework_scope.py
which write FrameworkApplicabilityResult / ControlApplicabilityResult): this module
only previews and is named with *Preview* dataclasses to avoid any clash with the
existing ControlApplicabilityResult model.
"""
from dataclasses import dataclass, field

from django.utils import timezone

from .smart_classification import (
    classify_company, OFFICIAL_FRAMEWORKS, official_control_count,
    REQUIRED, RECOMMENDED, OPTIONAL, NOT_INDICATED, _FW,
)

# Advisory applicability statuses (scope-based, NOT compliance).
APPLICABLE = 'applicable'
NOT_APPLICABLE = 'not_applicable'
NEEDS_INFO = 'needs_more_information'
LIKELY_APPLICABLE = 'likely_applicable'  # optional internal status (optional frameworks)

STATUS_AR = {
    APPLICABLE: 'قابلة للتطبيق',
    NOT_APPLICABLE: 'غير قابلة للتطبيق',
    NEEDS_INFO: 'تحتاج بيانات إضافية',
    LIKELY_APPLICABLE: 'مرجّح التطبيق',
}

_REASON = {
    APPLICABLE: ('يبدو أن هذا الضابط ينطبق على نطاق الشركة بناءً على البيانات الحالية.',
                 'This control appears to apply to the company scope based on current data.'),
    NOT_APPLICABLE: ('لا يبدو أن هذا الضابط ينطبق حاليًا بناءً على البيانات المتاحة.',
                     'This control does not appear to apply based on available data.'),
    NEEDS_INFO: ('نحتاج بيانات إضافية لتحديد قابلية تطبيق هذا الضابط.',
                 'More information is needed to determine applicability of this control.'),
    LIKELY_APPLICABLE: ('يُرجّح أن ينطبق هذا الضابط على نطاق الشركة (يتطلب تأكيد).',
                        'This control is likely in scope (needs confirmation).'),
}


@dataclass(frozen=True)
class ControlApplicabilityPreview:
    control_id: str
    framework_code: str
    title: str
    status: str
    reason_ar: str
    reason_en: str
    confidence: int
    tags: list = field(default_factory=list)

    @property
    def status_ar(self):
        return STATUS_AR.get(self.status, self.status)


@dataclass(frozen=True)
class FrameworkApplicabilityPreview:
    framework_code: str
    framework_name: str
    total_controls: int
    applicable_count: int
    not_applicable_count: int
    needs_more_information_count: int
    confidence: int
    status: str  # framework-level advisory status

    @property
    def status_ar(self):
        return STATUS_AR.get(self.status, self.status)


@dataclass(frozen=True)
class ApplicabilityPreview:
    company_id: int
    generated_at: object
    summaries: list = field(default_factory=list)
    controls: list = field(default_factory=list)
    missing_inputs: list = field(default_factory=list)
    next_action: str = ''
    overall_confidence: int = 0
    has_intake: bool = False

    @property
    def total_applicable(self):
        return sum(s.applicable_count for s in self.summaries)

    @property
    def total_controls(self):
        return sum(s.total_controls for s in self.summaries)


def _framework_status(classification_status, has_intake):
    """Map a Phase 6A classification status to a framework-level applicability status."""
    if classification_status in (REQUIRED, RECOMMENDED):
        return APPLICABLE
    if classification_status == OPTIONAL:
        return NEEDS_INFO  # likely in scope but needs confirmation
    # NOT_INDICATED
    return NOT_APPLICABLE if has_intake else NEEDS_INFO


def _control_tags(control, framework_code):
    tags = [framework_code]
    pr = getattr(control, 'priority', '')
    if pr:
        tags.append(pr)
    if getattr(control, 'is_mandatory', False):
        tags.append('mandatory')
    return tags


# R2 — condition tag -> "is this condition true for the company?" (intake signal).
# Only conditions with ONE reliable signal are here, so we can NARROW safely (never
# under-scope). A tag with no entry here never narrows anything.
CONDITION_SIGNALS = {
    'cloud': lambda p: bool(p.uses_cloud_services or p.provides_cloud_services),
    'critical_system': lambda p: bool(p.is_critical_system_operator),
    'remote_work': lambda p: bool(p.has_remote_work),
    'social_media': lambda p: bool(p.manages_official_social_media_accounts),
    'ot_ics': lambda p: bool(p.has_ot_environment),
}


def _refine_for_control(base_status, company, control):
    """Conservative per-control refinement using EXISTING control scope fields + condition tags.

    Narrows an 'applicable' framework result to 'not_applicable' only when the control
    explicitly excludes the company by sector/size, OR carries a condition tag (e.g. 'cloud')
    whose intake signal is definitively False. Requires an intake profile to narrow on a
    condition; never widens scope; never under-scopes on uncertainty.
    """
    if base_status != APPLICABLE:
        return base_status, None
    sectors = getattr(control, 'applies_to_sectors', None) or []
    sizes = getattr(control, 'applies_to_sizes', None) or []
    if sectors and company.sector and company.sector not in sectors:
        return NOT_APPLICABLE, 'هذا الضابط مخصّص لقطاعات محددة لا تشمل قطاع الشركة.'
    if sizes and company.size and company.size not in sizes:
        return NOT_APPLICABLE, 'هذا الضابط مخصّص لأحجام منشآت محددة لا تشمل حجم الشركة.'
    # R2: condition tags vs intake signals. Only narrow when an intake profile exists and the
    # required condition is definitively False (else stay applicable — no under-scoping).
    profile = getattr(company, 'intake_profile', None)
    if profile is not None:
        for tag in control.applicability_tags.values_list('tag', flat=True):
            check = CONDITION_SIGNALS.get(tag)
            if check is not None and not check(profile):
                return NOT_APPLICABLE, f'هذا الضابط مشروط بـ«{tag}» ولا ينطبق بناءً على بيانات إدخال الشركة.'
    return base_status, None


def evaluate_control_applicability(company, control) -> ControlApplicabilityPreview:
    """Advisory applicability for a single control (read-only)."""
    result = classify_company(company)
    recs = {r.code: r for r in result.recommendations}
    fv = getattr(control, 'framework_version', None)
    code = fv.code if fv is not None else getattr(getattr(control, 'framework', None), 'code', '')
    rec = recs.get(code)
    cls_status = rec.status if rec is not None else NOT_INDICATED
    confidence = rec.confidence if rec is not None else 50

    base = _framework_status(cls_status, result.has_intake)
    status, override_reason = _refine_for_control(base, company, control)
    reason_ar, reason_en = _REASON[status]
    if override_reason:
        reason_ar = override_reason

    title = getattr(control, 'title_ar', '') or getattr(control, 'title', '') or getattr(control, 'control_id', '')
    return ControlApplicabilityPreview(
        control_id=getattr(control, 'control_id', ''),
        framework_code=code,
        title=title,
        status=status,
        reason_ar=reason_ar,
        reason_en=reason_en,
        confidence=confidence,
        tags=_control_tags(control, code),
    )


def evaluate_company_applicability(company) -> ApplicabilityPreview:
    """Advisory applicability preview across all official frameworks (read-only)."""
    from .models import Control
    result = classify_company(company)
    recs = {r.code: r for r in result.recommendations}

    summaries, controls = [], []
    for f in OFFICIAL_FRAMEWORKS:
        code = f['code']
        rec = recs.get(code)
        cls_status = rec.status if rec is not None else NOT_INDICATED
        confidence = rec.confidence if rec is not None else 50
        fstatus = _framework_status(cls_status, result.has_intake)

        rows = list(Control.objects.filter(framework_version__code=code,
                                            is_legacy_import=False).select_related('domain'))
        applicable = not_applicable = needs_info = 0
        if rows:
            for ctrl in rows:
                status, override_reason = _refine_for_control(fstatus, company, ctrl)
                reason_ar, reason_en = _REASON[status]
                if override_reason:
                    reason_ar = override_reason
                title = getattr(ctrl, 'title_ar', '') or getattr(ctrl, 'title', '') or ctrl.control_id
                controls.append(ControlApplicabilityPreview(
                    control_id=ctrl.control_id, framework_code=code, title=title,
                    status=status, reason_ar=reason_ar, reason_en=reason_en,
                    confidence=confidence, tags=_control_tags(ctrl, code)))
                if status == APPLICABLE:
                    applicable += 1
                elif status == NOT_APPLICABLE:
                    not_applicable += 1
                else:
                    needs_info += 1
            total = len(rows)
        else:
            # Official controls not imported in this DB — fall back to the
            # authoritative total, allocated to the framework-level bucket.
            total = official_control_count(code)
            if fstatus == APPLICABLE:
                applicable = total
            elif fstatus == NOT_APPLICABLE:
                not_applicable = total
            else:
                needs_info = total

        summaries.append(FrameworkApplicabilityPreview(
            framework_code=code, framework_name=f['ar'], total_controls=total,
            applicable_count=applicable, not_applicable_count=not_applicable,
            needs_more_information_count=needs_info, confidence=confidence, status=fstatus))

    if not result.has_intake:
        next_action = 'أكمل ملف التصنيف لتدقيق قابلية تطبيق الضوابط قبل اعتماد النطاق.'
    else:
        next_action = 'راجع قابلية التطبيق ثم اعتمد النطاق وأنشئ خطة الضوابط مع المختص.'

    return ApplicabilityPreview(
        company_id=getattr(company, 'id', 0),
        generated_at=timezone.now(),
        summaries=summaries,
        controls=controls,
        missing_inputs=list(result.missing_inputs),
        next_action=next_action,
        overall_confidence=result.overall_confidence,
        has_intake=result.has_intake,
    )
