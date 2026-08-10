"""
Phase 6E — deterministic Rule Engine for SYSTEM-SUGGESTED (non-final) status.

Combines, with simple deterministic rules and NO AI/network:
* per-control applicability (Phase 6B preview),
* persisted text extraction (Phase 6C-FIX-A),
* persisted advisory AI analysis (Phase 6D),
into a framework-specific *suggested* compliance status. The result is ALWAYS a
suggestion "بانتظار مراجعة المدقق" — never a final decision, auditor verdict,
certification, or report finalization. It never writes ControlAssessment /
CompanyControl / reports.
"""
from dataclasses import dataclass, field

# Framework types.
FT_NCA = 'nca'
FT_ARAMCO_SABIC = 'aramco_sabic'

# Suggested statuses (must match EvidenceRuleEvaluation.SUGGESTED_AR keys).
S_C = 'suggested_c'
S_PC = 'suggested_pc'
S_NC = 'suggested_nc'
S_NA = 'suggested_na'
S_COMPLIANCE = 'suggested_compliance'
S_NONCOMPLIANCE = 'suggested_noncompliance'
S_NOT_APPLICABLE = 'suggested_not_applicable'
S_NEEDS_REVIEW = 'needs_review'
S_INSUFFICIENT = 'insufficient_data'


@dataclass(frozen=True)
class RuleEvaluationResult:
    suggested_status: str
    confidence: int
    rationale: str
    framework_type: str
    rule_signals: list = field(default_factory=list)
    missing_requirements: list = field(default_factory=list)


def _control_of(submission):
    try:
        return submission.checklist_item.evidence_requirement.control
    except Exception:
        return None


def _framework_type(control):
    fv = getattr(control, 'framework_version', None)
    code = fv.code if fv is not None else (getattr(getattr(control, 'framework', None), 'code', '') or '')
    code = code.upper()
    if code.startswith('NCA-'):
        return FT_NCA
    if code.startswith('ARAMCO') or code.startswith('SABIC'):
        return FT_ARAMCO_SABIC
    # Default to NCA vocabulary (most controls); still suggestion-only.
    return FT_NCA


def suggest_status_for_submission(submission) -> RuleEvaluationResult:
    """Pure deterministic suggestion (no persistence, no AI, no network)."""
    from .applicability_engine import evaluate_control_applicability, NOT_APPLICABLE
    from .evidence_ai_analyzer import can_analyze_submission

    control = _control_of(submission)
    ftype = _framework_type(control) if control is not None else FT_NCA
    nca = ftype == FT_NCA

    # 1) Not applicable -> suggested N/A.
    if control is not None:
        app = evaluate_control_applicability(submission.company, control)
        if app.status == NOT_APPLICABLE:
            return RuleEvaluationResult(
                suggested_status=S_NA if nca else S_NOT_APPLICABLE,
                confidence=80, framework_type=ftype,
                rationale='الضابط لا يبدو منطبقًا على نطاق الشركة بناءً على بيانات التصنيف وقابلية التطبيق.',
                rule_signals=['قابلية التطبيق: غير قابلة للتطبيق'])

    # 2) No extracted text -> insufficient data.
    ok_text, _ = can_analyze_submission(submission)
    if not ok_text:
        return RuleEvaluationResult(
            suggested_status=S_INSUFFICIENT, confidence=20, framework_type=ftype,
            rationale='لا يوجد نص مستخرج قابل للقراءة من الدليل.',
            rule_signals=['الاستخراج: لا يوجد نص قابل للقراءة'])

    # 3) Extracted text but no completed AI advisory analysis -> needs review.
    ai = getattr(submission, 'ai_analysis', None)
    if ai is None or ai.status != 'completed':
        return RuleEvaluationResult(
            suggested_status=S_NEEDS_REVIEW, confidence=40, framework_type=ftype,
            rationale='يوجد نص مستخرج، لكن لم يتم تشغيل التحليل الاستشاري بعد.',
            rule_signals=['الاستخراج: يوجد نص', 'التحليل الاستشاري: غير متوفر'])

    rel = ai.relevance
    missing = list(ai.missing_items or [])
    aic = int(ai.confidence or 0)
    signals = [f'التحليل الاستشاري: الارتباط={rel}', f'عناصر ناقصة={len(missing)}']

    # 4) High relevance, nothing missing -> suggested compliant.
    if rel == 'high' and not missing:
        return RuleEvaluationResult(
            suggested_status=S_C if nca else S_COMPLIANCE,
            confidence=min(aic, 90), framework_type=ftype,
            rationale='ارتباط مرتفع بالضابط دون عناصر ناقصة ظاهرة (اقتراح مبدئي).',
            rule_signals=signals, missing_requirements=missing)

    # 5) Medium relevance OR missing items -> partial (NCA) / needs review (Aramco/SABIC).
    if rel == 'medium' or missing:
        return RuleEvaluationResult(
            suggested_status=S_PC if nca else S_NEEDS_REVIEW,
            confidence=min(aic, 75), framework_type=ftype,
            rationale='ارتباط متوسط أو وجود عناصر ناقصة تحتاج إلى استكمال ومراجعة.',
            rule_signals=signals, missing_requirements=missing)

    # 6) Low relevance -> suggested non-compliant.
    if rel == 'low':
        return RuleEvaluationResult(
            suggested_status=S_NC if nca else S_NONCOMPLIANCE,
            confidence=min(aic, 70), framework_type=ftype,
            rationale='ارتباط منخفض بين الدليل والضابط (اقتراح مبدئي).',
            rule_signals=signals, missing_requirements=missing)

    # 7) Unclear -> needs review.
    return RuleEvaluationResult(
        suggested_status=S_NEEDS_REVIEW, confidence=min(aic, 50), framework_type=ftype,
        rationale='ارتباط غير واضح — يحتاج إلى مراجعة بشرية.',
        rule_signals=signals, missing_requirements=missing)


def evaluate_submission_rules(submission, actor=None):
    """Compute the suggestion and persist one EvidenceRuleEvaluation (upsert)."""
    from .models import EvidenceRuleEvaluation
    control = _control_of(submission)
    if control is None:
        obj, _ = EvidenceRuleEvaluation.objects.update_or_create(
            submission=submission,
            defaults=dict(status='skipped', suggested_status='', confidence=0, rationale='',
                          rule_signals=[], missing_requirements=[], framework_type='',
                          error_message='لا يوجد ضابط مرتبط بهذا الدليل.'))
        return obj
    try:
        r = suggest_status_for_submission(submission)
    except Exception:
        obj, _ = EvidenceRuleEvaluation.objects.update_or_create(
            submission=submission,
            defaults=dict(status='failed', suggested_status='', confidence=0, rationale='',
                          rule_signals=[], missing_requirements=[], framework_type='',
                          error_message='تعذر تنفيذ التقييم النظامي بأمان.'))
        return obj
    obj, _ = EvidenceRuleEvaluation.objects.update_or_create(
        submission=submission,
        defaults=dict(status='completed', suggested_status=r.suggested_status,
                      confidence=r.confidence, rationale=r.rationale,
                      rule_signals=r.rule_signals, missing_requirements=r.missing_requirements,
                      framework_type=r.framework_type, error_message=''))
    return obj
