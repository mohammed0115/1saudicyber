"""
Phase 3C — framework approval (scope) + control applicability planning.

Layer AFTER FrameworkApplicabilityResult (system recommendation) and BEFORE any
evidence checklist. It NEVER creates CompanyControl / Evidence / EvidenceRequirement,
and it plans ONLY official controls (framework_version set, is_legacy_import=False) —
never the legacy 334, never OTCC/DCC (which have no official controls).

Standalone module (not a `services/` package) to avoid colliding with compliance/services.py.
"""
from django.db import transaction
from django.utils import timezone

from compliance.models import (
    Control, FrameworkApplicabilityResult, CompanyFrameworkScope, ControlApplicabilityResult,
)

# Applicability decisions that should produce a proposed scope.
_PROPOSE_MAP = {
    'applicable': 'proposed',
    'manually_overridden': 'proposed',  # an applicable manual override still needs human approval
    'needs_review': 'needs_review',
    # 'not_applicable' -> intentionally no scope created.
}


def propose_framework_scopes(company, *, apply=False):
    """Create/update CompanyFrameworkScope rows from a company's applicability results.

    Returns a list of summary dicts. Only frameworks with official controls are eligible
    (FrameworkApplicabilityResult only ever exists for available frameworks, so OTCC/DCC
    are excluded automatically). Idempotent; never clobbers an already-approved/rejected scope.
    """
    out = []
    results = FrameworkApplicabilityResult.objects.filter(company=company).select_related('framework_version')
    for ar in results:
        target_status = _PROPOSE_MAP.get(ar.decision)
        if target_status is None:
            out.append({'framework': ar.framework_version.code, 'status': 'skipped',
                        'reason': f'applicability={ar.decision} (no scope proposed)'})
            continue
        entry = {'framework': ar.framework_version.code, 'status': target_status, 'reason': ar.reason}
        out.append(entry)
        if apply:
            existing = CompanyFrameworkScope.objects.filter(
                company=company, framework_version=ar.framework_version).first()
            if existing and existing.status in ('approved', 'rejected'):
                entry['status'] = existing.status  # preserve human decision
                continue
            CompanyFrameworkScope.objects.update_or_create(
                company=company, framework_version=ar.framework_version,
                defaults={'applicability_result': ar, 'status': target_status,
                          'source': 'applicability_result', 'reason': ar.reason})
    return out


def approve_framework_scope(scope, user=None):
    scope.status = 'approved'
    scope.approved_by = user
    scope.approved_at = timezone.now()
    scope.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
    return scope


def reject_framework_scope(scope, reason, user=None):
    scope.status = 'rejected'
    scope.rejected_by = user
    scope.rejected_at = timezone.now()
    scope.rejection_reason = reason or ''
    scope.save(update_fields=['status', 'rejected_by', 'rejected_at', 'rejection_reason', 'updated_at'])
    return scope


def reconcile_scope_after_reclassification(company):
    """F-AUDIT R1: after a re-classification, de-scope controls whose framework is no
    longer applicable — SOFT invalidation only, never a delete.

    For each CompanyFrameworkScope whose framework is now `not_applicable` (per the
    freshly-written FrameworkApplicabilityResult), flip its still-`applicable`
    ControlApplicabilityResult rows to `not_applicable` (so they drop out of checklist /
    assessment / gap generation, which all filter on decision='applicable') and mark the
    scope `rejected` (de-scoped).

    Deliberately preserved:
      * manual overrides — a `manually_overridden` framework never lands in the
        not_applicable set (evaluate_company keeps it), and CAR rows with decision
        `manually_overridden` are untouched (we only move `applicable` rows).
      * uploaded EvidenceSubmission files and AuditorFinalVerdict records — nothing is
        deleted, so no evidence or auditor decision is destroyed. A control that becomes
        applicable again on a later re-classification is simply re-planned to `applicable`.

    Idempotent (already-`rejected` scopes are skipped). Returns a summary dict.
    """
    not_applicable_fv_ids = set(
        FrameworkApplicabilityResult.objects
        .filter(company=company, decision='not_applicable')
        .values_list('framework_version_id', flat=True))
    if not not_applicable_fv_ids:
        return {'frameworks_descoped': 0, 'controls_descoped': 0}
    frameworks_descoped = 0
    controls_descoped = 0
    with transaction.atomic():
        stale_scopes = list(CompanyFrameworkScope.objects
                            .filter(company=company, framework_version_id__in=not_applicable_fv_ids)
                            .exclude(status='rejected'))
        for scope in stale_scopes:
            controls_descoped += (ControlApplicabilityResult.objects
                                  .filter(framework_scope=scope, decision='applicable')
                                  .update(decision='not_applicable'))
            scope.status = 'rejected'
            scope.rejection_reason = 'أُلغي النطاق تلقائيًا: لم يعد الإطار منطبقًا بعد إعادة التصنيف.'
            scope.save(update_fields=['status', 'rejection_reason', 'updated_at'])
            frameworks_descoped += 1
    return {'frameworks_descoped': frameworks_descoped, 'controls_descoped': controls_descoped}


def generate_control_applicability_plan(company, framework_scope, *, apply=False):
    """Plan official controls for an APPROVED framework scope.

    Returns (planned_count, list). Official controls only (framework_version set,
    is_legacy_import=False). Never creates CompanyControl/Evidence/EvidenceRequirement.
    Idempotent (update_or_create on company+control).
    """
    if framework_scope.status != 'approved':
        return 0, [{'status': 'skipped', 'reason': f'scope not approved (status={framework_scope.status})'}]

    controls = Control.objects.filter(
        framework_version=framework_scope.framework_version, is_legacy_import=False)
    planned = []
    for c in controls:
        planned.append(c.control_id)
        if apply:
            ControlApplicabilityResult.objects.update_or_create(
                company=company, control=c,
                defaults={'framework_scope': framework_scope, 'decision': 'applicable',
                          'reason': 'تم إدراج هذا الضابط لأن الإطار الأصلي معتمد.',
                          'source': 'framework_scope', 'confidence': 1.0})
    return len(planned), planned
