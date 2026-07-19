"""
F-AUDIT A1 — read-only canonical resolver for auditor per-control verdicts.

The platform records an auditor's per-control decision in THREE independent silos that
are never synced (no signals, no cross-writes):

  * ControlAssessment          keyed (company, control)              -> the documented
    "FINAL compliance decision"; the ONLY silo company-facing readiness / gap / commercial
    reports actually read (via gap_engine). Treated here as CANONICAL for reads.
  * AuditorControlVerdict      keyed (assessment, company_control)   -> what the auditor
    portal workflow writes; invisible to the company reports above.
  * AuditorFinalVerdict        keyed (evidence submission)           -> per-file verdict
    surfaced only in the internal auditor-reviewed report.

Because nothing reconciles them, the same (company, control) can hold conflicting
statuses. This module is PURE READ: it maps all three onto (company, control_id), applies
one normalization vocabulary, keeps ControlAssessment authoritative, and flags where the
silos DISAGREE so a human can reconcile. It never writes any model and never changes what
the reports read — it is an oversight overlay only.
"""

# AuditorFinalVerdict uses framework-specific codes; the other two already use the shared
# vocabulary (compliant / partially_compliant / non_compliant / not_applicable /
# needs_more_evidence / not_reviewed). Map the final_* codes onto that shared vocabulary.
_FINAL_TO_NORM = {
    'final_c': 'compliant', 'final_compliance': 'compliant',
    'final_pc': 'partially_compliant',
    'final_nc': 'non_compliant', 'final_noncompliance': 'non_compliant',
    'final_na': 'not_applicable', 'final_not_applicable': 'not_applicable',
    'needs_more_evidence': 'needs_more_evidence',
}

# Statuses that represent an actual decision (i.e. count toward a disagreement). A missing
# record or an explicit 'not_reviewed' is "no opinion" and never conflicts with anything.
_UNDECIDED = {'', None, 'not_reviewed'}


def _normalize(status, *, is_final=False):
    if status in _UNDECIDED:
        return None
    return _FINAL_TO_NORM.get(status, status) if is_final else status


def _control_of_submission(submission):
    try:
        return submission.checklist_item.evidence_requirement.control
    except Exception:
        return None


def resolve_control_verdicts(company):
    """Return {control_id: entry} across all three verdict silos for one company.

    entry = {
        'control_id', 'control_title',
        'control_assessment', 'auditor_control_verdict', 'auditor_final_verdict',  # normalized or None
        'canonical',            # ControlAssessment's normalized status (authoritative for reads)
        'distinct_decisions',   # sorted list of the distinct DECIDED statuses seen
        'has_disagreement',     # True iff >= 2 distinct decided statuses exist
    }
    Read-only — issues only SELECTs, mutates nothing.
    """
    from .models import (ControlAssessment, AuditorFinalVerdict)
    from auditor_portal.models import AuditorControlVerdict

    entries = {}

    def _entry(control):
        cid = getattr(control, 'control_id', None)
        if not cid:
            return None
        e = entries.get(cid)
        if e is None:
            e = {'control_id': cid,
                 'control_title': (getattr(control, 'title_ar', '') or getattr(control, 'title', '')),
                 'control_assessment': None,
                 'auditor_control_verdict': None,
                 'auditor_final_verdict': None}
            entries[cid] = e
        return e

    # 1) ControlAssessment (canonical) — one row per (company, control).
    for ca in (ControlAssessment.objects.filter(company=company)
               .select_related('control')):
        e = _entry(ca.control)
        if e is not None:
            e['control_assessment'] = _normalize(ca.status)

    # 2) AuditorControlVerdict (auditor-portal workflow) — one row per (assessment, control).
    #    A company may have several assessments; keep the most recently reviewed per control.
    seen_acv = {}
    for acv in (AuditorControlVerdict.objects.filter(assessment__company=company)
                .select_related('company_control__control')
                .order_by('-reviewed_at')):
        control = getattr(acv.company_control, 'control', None)
        cid = getattr(control, 'control_id', None)
        if not cid or cid in seen_acv:
            continue
        seen_acv[cid] = True
        e = _entry(control)
        if e is not None:
            e['auditor_control_verdict'] = _normalize(acv.status)

    # 3) AuditorFinalVerdict (per evidence submission) — collapse to the latest NON-STALE
    #    verdict per control (a stale verdict is on outdated evidence, see R2).
    seen_afv = {}
    for afv in (AuditorFinalVerdict.objects.filter(submission__company=company)
                .select_related('submission__checklist_item__evidence_requirement__control')
                .order_by('-reviewed_at')):
        control = _control_of_submission(afv.submission)
        cid = getattr(control, 'control_id', None)
        if not cid or cid in seen_afv or afv.is_stale:
            continue
        seen_afv[cid] = True
        e = _entry(control)
        if e is not None:
            e['auditor_final_verdict'] = _normalize(afv.status, is_final=True)

    for e in entries.values():
        decided = {s for s in (e['control_assessment'], e['auditor_control_verdict'],
                               e['auditor_final_verdict']) if s is not None}
        # Canonical precedence: the human ControlAssessment is authoritative; if it has no
        # opinion, fall back to the auditor-portal verdict, then the per-submission verdict.
        e['canonical'] = (e['control_assessment'] or e['auditor_control_verdict']
                          or e['auditor_final_verdict'])
        e['distinct_decisions'] = sorted(decided)
        e['has_disagreement'] = len(decided) >= 2
    return entries


def canonical_verdict(company, control_id):
    """THE single-source-of-truth read for one control's verdict (normalized status or None).

    Consolidates the parallel verdict silos behind one call: prefer the human
    ControlAssessment, else the auditor-portal verdict, else the per-submission verdict.
    Callers should read a control's compliance verdict through THIS, never a single raw
    model, so the display never depends on which silo happened to be written.
    """
    return resolve_control_verdicts(company).get(control_id, {}).get('canonical')


def company_verdict_disagreements(company):
    """Read-only list of controls whose verdict silos DISAGREE (most useful entries only).

    Returns a list of the resolver entries with has_disagreement=True, sorted by control_id.
    Empty list => every recorded verdict agrees (or only one silo has an opinion).
    """
    return sorted((e for e in resolve_control_verdicts(company).values() if e['has_disagreement']),
                  key=lambda e: e['control_id'])
