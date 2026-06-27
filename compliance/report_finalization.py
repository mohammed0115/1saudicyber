"""
Phase 7B — internal report finalization (auditor-reviewed report).

Aggregates persisted AuditorFinalVerdict records into a safe, read-only INTERNAL
review report. "Finalization" here means: surface the human auditor verdicts in a
report view — NOT issuing a certificate or any official accreditation. Read-only;
never updates ControlAssessment / CompanyControl / report calculations, never calls
AI/external services, and never exposes file paths, secrets, raw extracted text, or
raw AI responses.
"""
from dataclasses import dataclass, field

MAX_RATIONALE_EXCERPT = 200


@dataclass(frozen=True)
class VerdictRow:
    control_id: str
    control_title: str
    framework_code: str
    rule_suggestion_ar: str
    verdict_status: str
    verdict_status_ar: str
    confidence: int
    rationale_excerpt: str
    required_actions_count: int
    reviewed_at: object
    reviewer_label: str
    submission_id: int


@dataclass(frozen=True)
class AuditorReviewedReport:
    total_submissions: int
    reviewed_count: int
    pending_count: int
    status_counts: dict = field(default_factory=dict)
    status_counts_ar: dict = field(default_factory=dict)
    framework_counts: dict = field(default_factory=dict)
    latest_reviewed_at: object = None
    rows: list = field(default_factory=list)

    @property
    def has_verdicts(self):
        return self.reviewed_count > 0


def _reviewer_label(user):
    if user is None:
        return 'مراجع داخلي'
    name = (user.get_full_name() or '').strip()
    return name or 'مراجع داخلي'


def _control_of(submission):
    try:
        return submission.checklist_item.evidence_requirement.control
    except Exception:
        return None


def build_auditor_reviewed_report(company) -> AuditorReviewedReport:
    """Aggregate this company's AuditorFinalVerdict records (read-only)."""
    from .models import EvidenceSubmission, AuditorFinalVerdict, EvidenceRuleEvaluation

    total_submissions = EvidenceSubmission.objects.filter(company=company).count()
    verdicts = (AuditorFinalVerdict.objects
                .filter(submission__company=company)
                .select_related('submission__checklist_item__evidence_requirement__control',
                                'submission__checklist_item__evidence_requirement__control__framework_version',
                                'reviewer', 'source_rule_evaluation')
                .order_by('-reviewed_at'))

    status_counts, status_counts_ar, framework_counts = {}, {}, {}
    rows = []
    latest = None
    for v in verdicts:
        status_counts[v.status] = status_counts.get(v.status, 0) + 1
        status_counts_ar[v.status_ar] = status_counts_ar.get(v.status_ar, 0) + 1
        ft = v.framework_type or 'unknown'
        framework_counts[ft] = framework_counts.get(ft, 0) + 1
        if latest is None or (v.reviewed_at and v.reviewed_at > latest):
            latest = v.reviewed_at
        control = _control_of(v.submission)
        cid = getattr(control, 'control_id', '') if control else ''
        ctitle = (getattr(control, 'title_ar', '') or getattr(control, 'title', '')) if control else ''
        fv = getattr(control, 'framework_version', None) if control else None
        fcode = fv.code if fv is not None else (getattr(getattr(control, 'framework', None), 'code', '') if control else '')
        rule = v.source_rule_evaluation or getattr(v.submission, 'rule_evaluation', None)
        rule_ar = rule.suggested_status_ar if (rule and rule.status == 'completed') else '—'
        rows.append(VerdictRow(
            control_id=cid, control_title=ctitle, framework_code=fcode,
            rule_suggestion_ar=rule_ar, verdict_status=v.status, verdict_status_ar=v.status_ar,
            confidence=v.confidence, rationale_excerpt=(v.rationale or '')[:MAX_RATIONALE_EXCERPT],
            required_actions_count=len(v.required_actions or []), reviewed_at=v.reviewed_at,
            reviewer_label=_reviewer_label(v.reviewer), submission_id=v.submission_id))

    reviewed_count = len(rows)
    return AuditorReviewedReport(
        total_submissions=total_submissions,
        reviewed_count=reviewed_count,
        pending_count=max(0, total_submissions - reviewed_count),
        status_counts=status_counts,
        status_counts_ar=status_counts_ar,
        framework_counts=framework_counts,
        latest_reviewed_at=latest,
        rows=rows,
    )
