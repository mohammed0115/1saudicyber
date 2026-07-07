"""
Phase 6F — Auditor Final Verdict (human review decision, internal-only).

Records a human reviewer's final verdict for an EvidenceSubmission, with full
review context (extraction, advisory AI, rule-engine suggestion). This is an
INTERNAL platform decision — NOT an official certification or accreditation. It
never issues a certificate, never finalizes external reports, never bulk-creates
CompanyControl, and never calls AI or external services.

Authorization: staff/superuser, or an ACTIVE auditor with an ACCEPTED assignment
to the submission's company. Company users may only VIEW their own verdict.
"""
from django.db import transaction

from .rule_engine import _framework_type, FT_NCA, FT_ARAMCO_SABIC, _control_of

# Allowed verdict statuses per framework type (+ shared needs_more_evidence).
NCA_STATUSES = {'final_c', 'final_pc', 'final_nc', 'final_na'}
ARAMCO_SABIC_STATUSES = {'final_compliance', 'final_noncompliance', 'final_not_applicable'}
SHARED_STATUSES = {'needs_more_evidence'}


class VerdictError(Exception):
    """Raised for invalid verdict input (permission/status/rationale)."""


def _is_assigned_auditor(user, company):
    """True if user is an ACTIVE auditor with an ACCEPTED assignment to the company."""
    from auditors.services import get_auditor_profile
    from auditors.models import AuditorAssignment
    profile = get_auditor_profile(user)
    # is_active_auditor is a @property — a pending/suspended auditor evaluates False here
    # (the old naked-method reference was always truthy = a silent auth bypass).
    if profile is None or not profile.is_active_auditor:
        return False
    return AuditorAssignment.objects.filter(
        company=company, auditor=profile, status='accepted').exists()


def can_submit_final_verdict(user, submission):
    """Only staff/superuser or an assigned active auditor may submit a verdict.

    Independence (P1-5): nobody affiliated with the audited company may sign its verdict —
    a conflict of interest — even a staff member who belongs to that company. Auditors are
    platform-side (no company link) so this only blocks true self-audits.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'company_id', None) is not None and user.company_id == submission.company_id:
        return False
    if user.is_staff or user.is_superuser:
        return True
    return _is_assigned_auditor(user, submission.company)


def can_view_submission_review(user, submission):
    """Owner company user, staff/superuser, or assigned auditor may view the review."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_staff or user.is_superuser:
        return True
    if getattr(user, 'company_id', None) == submission.company_id:
        return True
    return _is_assigned_auditor(user, submission.company)


def framework_type_for(submission):
    control = _control_of(submission)
    return _framework_type(control) if control is not None else FT_NCA


def allowed_statuses_for(submission):
    ft = framework_type_for(submission)
    base = NCA_STATUSES if ft == FT_NCA else ARAMCO_SABIC_STATUSES
    return sorted(base | SHARED_STATUSES)


def record_auditor_final_verdict(submission, reviewer, status, rationale,
                                 confidence=None, required_actions=None):
    """Validate and upsert one AuditorFinalVerdict per submission (latest wins)."""
    from .models import AuditorFinalVerdict
    if not can_submit_final_verdict(reviewer, submission):
        raise VerdictError('ليس لديك صلاحية لتسجيل قرار المدقق.')
    ft = framework_type_for(submission)
    allowed = (NCA_STATUSES if ft == FT_NCA else ARAMCO_SABIC_STATUSES) | SHARED_STATUSES
    if status not in allowed:
        raise VerdictError('حالة القرار غير صالحة لهذا الإطار.')
    if not (rationale or '').strip():
        raise VerdictError('سبب القرار مطلوب.')
    try:
        conf = int(confidence) if confidence is not None else 0
    except (TypeError, ValueError):
        conf = 0
    conf = max(0, min(100, conf))
    actions = [a.strip()[:240] for a in (required_actions or []) if isinstance(a, str) and a.strip()][:12]
    with transaction.atomic():
        obj, _ = AuditorFinalVerdict.objects.update_or_create(
            submission=submission,
            defaults=dict(reviewer=reviewer, status=status, confidence=conf,
                          rationale=rationale.strip(), required_actions=actions,
                          framework_type=ft, source_rule_evaluation=getattr(submission, 'rule_evaluation', None)),
        )
        # Advance the evidence-FILE lifecycle so it no longer reads pending_review after a
        # human review. status here = "was this file reviewed/accepted as evidence", NOT the
        # compliance judgment (which stays in AuditorFinalVerdict). So any final verdict
        # accepts the file; only 'needs_more_evidence' asks for a re-upload. A non-compliant
        # verdict is NOT a rejected file.
        new_status = 'needs_reupload' if status == 'needs_more_evidence' else 'accepted'
        if submission.status != new_status:
            update_fields = ['status', 'updated_at']
            submission.status = new_status
            if new_status == 'needs_reupload':
                submission.rejection_reason = rationale.strip()[:1000]
                update_fields.append('rejection_reason')
            elif submission.rejection_reason:
                # Clear a stale re-upload reason left over from a prior needs_more_evidence.
                submission.rejection_reason = ''
                update_fields.append('rejection_reason')
            submission.save(update_fields=update_fields)
    return obj
