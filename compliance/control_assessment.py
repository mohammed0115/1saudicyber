"""
Phase 3G — auditor-driven control assessment.

ControlAssessment is the FINAL compliance decision and is created/updated by an
auditor/staff ONLY. AI/evidence never set the final status here. Official controls
only (framework_version set, is_legacy_import=False); legacy 334 is excluded.
Reads the latest EvidenceAnalysisResult as ADVISORY context only.

Standalone module (not a `services/` package) to avoid colliding with compliance/services.py.
"""
from django.utils import timezone

from compliance.models import (
    ControlApplicabilityResult, ControlAssessment, EvidenceAnalysisResult,
)

# Fields an auditor may set via update_assessment_from_auditor_input.
_AUDITOR_FIELDS = {
    'status', 'score', 'auditor_notes', 'remediation_required', 'remediation_plan',
    'remediation_due_date', 'risk_level', 'confidence_level', 'evidence_summary',
}
_VALID_STATUSES = {c[0] for c in ControlAssessment.STATUS_CHOICES}


def _latest_ai_snapshot(company, control):
    """Return the latest AI advisory summary for traceability (NOT a decision)."""
    a = (EvidenceAnalysisResult.objects
         .filter(company=company, control=control)
         .order_by('-created_at').first())
    return a.summary if a else ''


def get_or_create_assessment_for_control(company, control, *, user=None, apply=False):
    """Ensure a not_reviewed ControlAssessment exists for an official control. Idempotent."""
    if control.framework_version_id is None or control.is_legacy_import:
        return None, False  # official controls only
    if not apply:
        exists = ControlAssessment.objects.filter(company=company, control=control).exists()
        return None, (not exists)
    car = (ControlApplicabilityResult.objects
           .filter(company=company, control=control).first())
    obj, created = ControlAssessment.objects.get_or_create(
        company=company, control=control,
        defaults={'status': 'not_reviewed', 'control_applicability_result': car,
                  'framework_scope': car.framework_scope if car else None,
                  'ai_summary_snapshot': _latest_ai_snapshot(company, control)})
    return obj, created


def create_assessments_for_company(company, *, apply=False):
    """Create not_reviewed assessments for the company's APPLICABLE OFFICIAL controls.

    Never creates CompanyControl, never generates reports, never sets a final status.
    """
    cars = (ControlApplicabilityResult.objects
            .filter(company=company, decision='applicable')
            .select_related('control'))
    created = existing = 0
    for car in cars:
        control = car.control
        if control.framework_version_id is None or control.is_legacy_import:
            continue
        _, was_created = get_or_create_assessment_for_control(company, control, apply=apply)
        if apply:
            created += int(was_created); existing += int(not was_created)
        else:
            created += int(was_created)
    return {'created': created, 'existing': existing}


def update_assessment_from_auditor_input(assessment, data, user):
    """Apply an auditor's manual decision. The ONLY path that sets a final status."""
    for field in _AUDITOR_FIELDS:
        if field in data:
            if field == 'status' and data[field] not in _VALID_STATUSES:
                continue
            setattr(assessment, field, data[field])
    assessment.reviewed_by = user
    assessment.reviewed_at = timezone.now()
    assessment.save()
    return assessment
