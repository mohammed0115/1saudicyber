"""P0-02 — assessment completion policy, scope/evidence snapshots (fail-closed).

Central, code-derived preconditions for finalizing an internal review. Where the product has
no explicit business rule the SAFE (fail-closed) choice is taken and flagged for Product — no
rule is invented.

Scope of an assessment = the company's CompanyControls (the set submit_report already counts).
A control is FINALLY reviewed iff it carries an AuditorControlVerdict in a FINAL state
(compliant / partially_compliant / non_compliant / not_applicable). 'needs_more_evidence' and
'not_reviewed'/absent are NOT final. Completion requires EVERY in-scope control finally
reviewed, for pass, conditional_pass AND fail.
"""
import hashlib

# Final (decisive) control-verdict states — 'needs_more_evidence' is explicitly NOT final.
FINAL_VERDICT_STATES = frozenset({'compliant', 'partially_compliant', 'non_compliant', 'not_applicable'})
BLOCKING_FINDING_SEVERITIES = frozenset({'major_nc'})


class CompletionError(Exception):
    """A completion precondition failed. Carries a user-facing Arabic message (no cross-tenant data)."""
    def __init__(self, message_ar):
        self.message_ar = message_ar
        super().__init__(message_ar)


class EvidenceUnavailable(Exception):
    """An evidence file could not be read while hashing the snapshot — issuance must fail-closed."""


def assess_completion(assessment):
    """Read-only scope/review census for the assessment. Returns counts + per-control rows."""
    from auditor_portal.models import AuditorControlVerdict, AuditFinding, DocumentRequest
    from compliance.models import CompanyControl
    scope = list(CompanyControl.objects.filter(company=assessment.company)
                 .select_related('control', 'control__framework').order_by('id'))
    verdicts = {v.company_control_id: v for v in AuditorControlVerdict.objects.filter(
        assessment=assessment, company_control_id__in=[cc.id for cc in scope])}
    reviewed = compliant = non_compliant = not_applicable = 0
    missing = []
    rows = []
    for cc in scope:
        v = verdicts.get(cc.id)
        final = v is not None and v.status in FINAL_VERDICT_STATES
        if final:
            reviewed += 1
            if v.status == 'compliant':
                compliant += 1
            elif v.status == 'non_compliant':
                non_compliant += 1
            elif v.status == 'not_applicable':
                not_applicable += 1
        else:
            missing.append(cc.id)
        rows.append({
            'company_control_id': cc.id,
            'control_code': getattr(cc.control, 'control_id', ''),
            'framework': getattr(getattr(cc.control, 'framework', None), 'code', ''),
            'applicability': cc.status,
            'verdict': v.status if v is not None else None,
            'verdict_at': v.reviewed_at.isoformat() if (v is not None and v.reviewed_at) else None,
        })
    open_blocking = AuditFinding.objects.filter(
        assessment=assessment, severity__in=BLOCKING_FINDING_SEVERITIES,
        status__in=AuditFinding.OPEN_STATES).count()
    open_rfi = DocumentRequest.objects.filter(
        assessment=assessment, status__in=DocumentRequest.OPEN_STATES).count()
    return {
        'scope_count': len(scope), 'reviewed_count': reviewed, 'missing_count': len(missing),
        'compliant_count': compliant, 'non_compliant_count': non_compliant,
        'not_applicable_count': not_applicable, 'open_findings_count': open_blocking,
        'open_rfi_count': open_rfi, 'rows': rows,
    }


def validate_ready_for_completion(assessment, actor, final_verdict):
    """Raise CompletionError on the first failed precondition, else return the census dict.

    Fail-closed: legal state; actor is the CURRENTLY assigned, live-accepted, ACTIVE auditor;
    report not already issued; no open RFI; verdict valid; EVERY in-scope control finally
    reviewed (missing_count == 0); and verdict consistent (a passing verdict cannot coexist with
    a non-compliant control or an open blocking finding). The precise pass/conditional_pass
    business policy is a Product decision — this is the safe minimum.
    """
    from auditor_portal.models import AuditReport
    from auditors.services import has_accepted_assignment, get_auditor_profile

    if not assessment.can_transition_to('completed'):
        raise CompletionError('لا يمكن إصدار التقرير من حالة التقييم الحالية.')
    if assessment.assigned_auditor_id != getattr(actor, 'id', None):
        raise CompletionError('لا يمكن إنهاء تقييم غير مُسنَد إليك.')
    if not has_accepted_assignment(actor, assessment.company):
        raise CompletionError('إسنادك لهذه الشركة لم يعد فعّالًا.')
    profile = get_auditor_profile(actor)
    if profile is None or not profile.is_active_auditor:
        raise CompletionError('حساب المدقّق غير فعّال.')
    if AuditReport.objects.filter(assessment=assessment).exists():
        raise CompletionError('التقرير الداخلي لهذا التقييم مُصدَر بالفعل.')

    if final_verdict not in dict(AuditReport._meta.get_field('verdict').choices):
        raise CompletionError('قيمة الحكم النهائي غير صالحة أو مفقودة.')

    census = assess_completion(assessment)
    if census['open_rfi_count']:
        raise CompletionError('لا يمكن الإصدار قبل إغلاق طلبات الاستكمال المفتوحة.')
    # Completeness: every in-scope control must have a FINAL verdict (message leaks no per-tenant data).
    if census['missing_count'] > 0:
        raise CompletionError(
            'لا يمكن إصدار الحكم النهائي قبل مراجعة جميع الضوابط ضمن النطاق '
            '(%d ضابطًا دون حكم نهائي).' % census['missing_count'])
    # Consistency: a passing verdict cannot coexist with a non-compliant control or an open
    # blocking (major non-conformity) finding.
    if final_verdict == 'pass' and (census['non_compliant_count'] > 0 or census['open_findings_count'] > 0):
        raise CompletionError('لا يمكن منح «متوافق» مع وجود ضوابط غير متوافقة أو ملاحظات حرجة مفتوحة.')
    return census


def build_scope_snapshot(census):
    """The frozen per-control scope of the issue (proves required vs reviewed count)."""
    return list(census['rows'])


def compute_evidence_snapshot(company):
    """Fail-closed evidence snapshot: SHA-256 computed from the ACTUAL file bytes at issue time.

    Raises EvidenceUnavailable if any referenced evidence file cannot be opened/read — the caller
    runs this inside the completion transaction, so a failure rolls back the ENTIRE issuance (no
    partial report, no 'completed'). Submissions without a stored file are skipped (nothing to hash).
    """
    from compliance.models import EvidenceSubmission
    snapshot = []
    for s in EvidenceSubmission.objects.filter(company=company).order_by('id'):
        if not s.uploaded_file:
            continue
        try:
            with s.uploaded_file.open('rb') as fh:
                digest = hashlib.sha256()
                for chunk in iter(lambda: fh.read(65536), b''):
                    digest.update(chunk)
        except (OSError, ValueError) as exc:
            raise EvidenceUnavailable(
                'تعذّرت قراءة ملف دليل مطلوب للتقرير (id=%s).' % s.id) from exc
        snapshot.append({
            'submission_id': s.id, 'filename': s.original_filename,
            'sha256': digest.hexdigest(), 'version': s.version, 'size': s.file_size,
        })
    return snapshot
