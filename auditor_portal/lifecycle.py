"""P0-02 — assessment completion policy + report snapshot (fail-closed).

Central preconditions for finalizing an internal review, derived from the ACTUAL product flow.
Where the product has no explicit business rule, the SAFE (fail-closed) choice is taken and the
need for a Product decision is called out in comments — no business rule is invented.
"""


class CompletionError(Exception):
    """A completion precondition failed. Carries a user-facing Arabic message."""
    def __init__(self, message_ar):
        self.message_ar = message_ar
        super().__init__(message_ar)


def validate_ready_for_completion(assessment, actor, final_verdict):
    """Raise CompletionError(message_ar) on the first failed precondition, else return None.

    Checks (all from real code):
      * legal state — only 'auditor_review' -> 'completed' is allowed;
      * actor is the CURRENTLY assigned auditor with a LIVE accepted assignment and an ACTIVE profile;
      * the report has not already been issued (write-once);
      * no blocking (open) RFI;
      * final verdict is valid AND consistent — 'pass' cannot coexist with a non-compliant control
        verdict (fail-closed; the exact pass/conditional_pass policy is a Product decision).
    """
    from auditor_portal.models import AuditReport, AuditorControlVerdict, DocumentRequest
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

    if DocumentRequest.objects.filter(
            assessment=assessment, status__in=DocumentRequest.OPEN_STATES).exists():
        raise CompletionError('لا يمكن الإصدار قبل إغلاق طلبات الاستكمال المفتوحة.')

    if final_verdict not in dict(AuditReport._meta.get_field('verdict').choices):
        raise CompletionError('قيمة الحكم النهائي غير صالحة أو مفقودة.')
    # Consistency: a passing verdict cannot coexist with a non-compliant control verdict.
    if final_verdict == 'pass' and AuditorControlVerdict.objects.filter(
            assessment=assessment, status='non_compliant').exists():
        raise CompletionError('لا يمكن منح «متوافق» مع وجود ضوابط غير متوافقة — استخدم حكمًا متسقًا.')


def build_evidence_snapshot(company):
    """Immutable reference (id + filename + hash + version) to every evidence submission that
    exists at issue time. Lets the report prove which evidence version it was built on; later
    company evidence uploads create NEW rows and never alter this snapshot (P0-02 Evidence Option B)."""
    from compliance.models import EvidenceSubmission
    return [{
        'submission_id': s.id,
        'filename': s.original_filename,
        'file_hash': s.file_hash,
        'version': s.version,
    } for s in EvidenceSubmission.objects.filter(company=company).order_by('id')]
