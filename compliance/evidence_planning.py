"""
Phase 3D — evidence requirement templates + company checklist planning.

Builds reusable EvidenceRequirement templates (one default per official control)
and company-specific EvidenceChecklistItem PLANS. It NEVER creates Evidence,
CompanyControl, or EvidenceSubmission, never changes the upload flow, and only
ever works with OFFICIAL controls (framework_version set, is_legacy_import=False).

Standalone module (not a `services/` package) to avoid colliding with compliance/services.py.
"""
from compliance.models import (
    Control, EvidenceRequirement, EvidenceChecklistItem, ControlApplicabilityResult,
)

# A generic default requirement is NOT an official mapping — it is a starter task.
_DEFAULT_TITLE = 'Primary supporting evidence'
_DEFAULT_DESC = ('Provide a document/record demonstrating implementation of this control. '
                 'This is a generic default starter task, not an official evidence mapping.')


def _is_official(control):
    return control.framework_version_id is not None and not control.is_legacy_import


def create_default_requirement_for_control(control, *, apply=False):
    """Ensure a default EvidenceRequirement exists for an OFFICIAL control. Idempotent.

    Returns (requirement_or_None, created_bool). Skips legacy/non-official controls.
    """
    if not _is_official(control):
        return None, False
    if not apply:
        exists = EvidenceRequirement.objects.filter(control=control, title=_DEFAULT_TITLE).exists()
        return None, (not exists)
    req, created = EvidenceRequirement.objects.get_or_create(
        control=control, title=_DEFAULT_TITLE,
        defaults={'description': _DEFAULT_DESC, 'evidence_type': control.evidence_type or 'policy',
                  'requirement_level': 'mandatory', 'source': 'default_template',
                  'source_reference': f'Default starter task for {control.external_reference or control.control_id}',
                  'sort_order': 0})
    return req, created


def generate_evidence_requirements(*, apply=False, framework_version_code=None):
    """Create default requirements for all official controls (optionally one framework version)."""
    controls = Control.objects.filter(framework_version__isnull=False, is_legacy_import=False)
    if framework_version_code:
        controls = controls.filter(framework_version__code=framework_version_code)
    created = existing = 0
    for c in controls:
        _, was_created = create_default_requirement_for_control(c, apply=apply)
        if apply:
            created += int(was_created); existing += int(not was_created)
        else:
            created += int(was_created)
    return {'official_controls': controls.count(), 'created': created, 'existing': existing}


def _plan_for_result(company, car, *, apply):
    """Plan checklist items for one ControlApplicabilityResult (official control)."""
    control = car.control
    if not _is_official(control) or car.decision != 'applicable':
        return 0
    reqs = EvidenceRequirement.objects.filter(control=control, is_active=True)
    n = 0
    for req in reqs:
        n += 1
        if apply:
            EvidenceChecklistItem.objects.get_or_create(
                company=company, evidence_requirement=req,
                defaults={'control_applicability_result': car, 'status': 'planned',
                          'priority': 'high' if control.priority == 'critical' else 'medium'})
    return n


def generate_evidence_checklist_for_framework_scope(scope, *, apply=False):
    """Plan checklist items for the applicable official controls under an approved scope."""
    if scope.status != 'approved':
        return {'status': 'skipped', 'reason': f'scope not approved ({scope.status})', 'planned': 0}
    cars = ControlApplicabilityResult.objects.filter(
        company=scope.company, framework_scope=scope, decision='applicable').select_related('control')
    planned = sum(_plan_for_result(scope.company, car, apply=apply) for car in cars)
    return {'status': 'ok', 'framework': scope.framework_version.code, 'planned': planned}


def generate_evidence_checklist_for_company(company, *, apply=False):
    """Plan checklist items across all the company's applicable official controls."""
    cars = (ControlApplicabilityResult.objects
            .filter(company=company, decision='applicable')
            .select_related('control', 'control__framework_version'))
    planned = sum(_plan_for_result(company, car, apply=apply) for car in cars)
    return {'company': company.id, 'planned': planned}
