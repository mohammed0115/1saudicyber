"""
G2 — Audit findings & corrective-action (CAPA) service + G1 maturity scoring.

Pure operations over AuditFinding / CorrectiveAction / AuditorControlVerdict. Tenant/
assignment authorization is enforced by the calling view (mirroring save_verdict, which
scopes the Assessment to assigned_auditor); these functions validate inputs and lifecycle
transitions only. Internal readiness review — never an official certification.
"""
from collections import defaultdict

from django.db import transaction


# ── G2: Findings ───────────────────────────────────────────────────────────────
def create_finding(assessment, company_control, auditor, *, severity, title, description,
                   root_cause='', evidence_reference=''):
    from .models import AuditFinding
    if severity not in dict(AuditFinding.SEVERITY_CHOICES):
        raise ValueError('invalid severity')
    if not (title or '').strip() or not (description or '').strip():
        raise ValueError('title and description are required')
    return AuditFinding.objects.create(
        assessment=assessment, company_control=company_control, auditor=auditor,
        severity=severity, title=title.strip()[:255], description=description.strip(),
        root_cause=(root_cause or '').strip(), evidence_reference=(evidence_reference or '').strip()[:255])


# Allowed finding lifecycle transitions (open → remediation → re-verify → closed, with reopen).
_FINDING_TRANSITIONS = {
    'open': {'in_remediation', 'closed'},
    'in_remediation': {'reverify', 'closed'},
    'reverify': {'closed', 'reopened'},
    'closed': {'reopened'},
    'reopened': {'in_remediation', 'closed'},
}


def transition_finding(finding, new_status):
    from .models import AuditFinding
    if new_status not in dict(AuditFinding.STATUS_CHOICES):
        raise ValueError('invalid status')
    if new_status not in _FINDING_TRANSITIONS.get(finding.status, set()):
        raise ValueError('invalid transition %s -> %s' % (finding.status, new_status))
    finding.status = new_status
    finding.save(update_fields=['status', 'updated_at'])
    return finding


# ── G2: Corrective actions (CAPA) ──────────────────────────────────────────────
def add_corrective_action(finding, *, description, owner='', due_date=None, created_by=None):
    from .models import CorrectiveAction
    if not (description or '').strip():
        raise ValueError('description is required')
    with transaction.atomic():
        action = CorrectiveAction.objects.create(
            finding=finding, description=description.strip(), owner=(owner or '').strip()[:160],
            due_date=due_date, created_by=created_by)
        # The first CAPA moves an open finding into remediation.
        if finding.status == 'open':
            finding.status = 'in_remediation'
            finding.save(update_fields=['status', 'updated_at'])
    return action


def verify_corrective_action(action, *, note='', mark_verified=True):
    action.verification_note = (note or '').strip()
    if mark_verified:
        action.status = 'verified'
    action.save(update_fields=['status', 'verification_note', 'updated_at'])
    return action


# CAPA progress transitions the COMPANY drives (planned → in_progress → done); the auditor
# then verifies (done → verified via verify_corrective_action). 'done' can bounce back.
_CAPA_TRANSITIONS = {
    'planned': {'in_progress', 'done'},
    'in_progress': {'done'},
    'done': {'in_progress'},
    'verified': set(),
}


def advance_corrective_action(action, new_status):
    """Move a CAPA to 'in_progress' or 'done' (the company-side remediation handshake)."""
    if new_status not in {'in_progress', 'done'}:
        raise ValueError('invalid capa status')
    if new_status not in _CAPA_TRANSITIONS.get(action.status, set()):
        raise ValueError('invalid transition %s -> %s' % (action.status, new_status))
    action.status = new_status
    action.save(update_fields=['status', 'updated_at'])
    return action


# ── G1: Maturity / compliance % from implementation levels ─────────────────────
def assessment_maturity(assessment):
    """Compliance % from AuditorControlVerdict.implementation_level for one assessment,
    grouped by control domain. `not_applicable` / unset are excluded from the denominator.

    Returns {overall_pct, assessed_count, domains: [{name, pct, count}, ...]}. Read-only.
    """
    from .models import AuditorControlVerdict
    weight = AuditorControlVerdict.IMPLEMENTATION_WEIGHT
    per_domain = defaultdict(lambda: {'scored': 0.0, 'count': 0})
    overall = {'scored': 0.0, 'count': 0}
    verdicts = (AuditorControlVerdict.objects
                .filter(assessment=assessment)
                .exclude(implementation_level='')
                .select_related('company_control__control__domain'))
    for v in verdicts:
        w = weight.get(v.implementation_level)   # not_applicable -> None -> skip
        if w is None:
            continue
        control = getattr(v.company_control, 'control', None)
        dom = getattr(getattr(control, 'domain', None), 'name', None) or 'غير مصنّف'
        per_domain[dom]['scored'] += w
        per_domain[dom]['count'] += 1
        overall['scored'] += w
        overall['count'] += 1

    def pct(d):
        return round(d['scored'] / d['count'] * 100) if d['count'] else 0

    return {
        'overall_pct': pct(overall),
        'assessed_count': overall['count'],
        'domains': [{'name': k, 'pct': pct(v), 'count': v['count']}
                    for k, v in sorted(per_domain.items())],
    }
