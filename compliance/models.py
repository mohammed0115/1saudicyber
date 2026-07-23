"""
Compliance Models - Frameworks, Controls, Evidence, Assessments
"""
from django.db import models
from core.models import Company, User
from core.storage import private_media_storage  # P0-01: private evidence storage


class InvalidAssessmentTransition(Exception):
    """Raised when an Assessment is asked to make a transition its state machine forbids (P0-02)."""


class Framework(models.Model):
    """Compliance framework (NCA ECC, Aramco SACS-002, SABIC CyberTrust)."""
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    name_ar = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    version = models.CharField(max_length=20, blank=True)
    total_controls = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'frameworks'

    def __str__(self):
        return self.name


class Domain(models.Model):
    """Control domain/category within a framework."""
    framework = models.ForeignKey(Framework, on_delete=models.CASCADE, related_name='domains')
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    name_ar = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'domains'
        ordering = ['order']

    def __str__(self):
        return f"{self.framework.code} - {self.name}"


class Control(models.Model):
    """Individual compliance control/requirement."""
    PRIORITY_CHOICES = [
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    EVIDENCE_TYPE_CHOICES = [
        ('policy', 'Policy Document'),
        ('procedure', 'Procedure Document'),
        ('screenshot', 'System Screenshot'),
        ('config', 'Configuration Export'),
        ('report', 'Audit/Scan Report'),
        ('log', 'System Log'),
        ('interview', 'Interview Record'),
        ('certificate', 'Certificate/License'),
        ('other', 'Other'),
    ]

    framework = models.ForeignKey(Framework, on_delete=models.CASCADE, related_name='controls')
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name='controls')
    control_id = models.CharField(max_length=50)
    title = models.CharField(max_length=500)
    title_ar = models.CharField(max_length=500, blank=True)
    description = models.TextField()
    description_ar = models.TextField(blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    evidence_type = models.CharField(max_length=20, choices=EVIDENCE_TYPE_CHOICES, default='policy')
    evidence_guidance = models.TextField(blank=True)
    evidence_guidance_ar = models.TextField(blank=True)

    # Cross-mapping
    mapped_controls = models.ManyToManyField('self', blank=True, symmetrical=True)

    # Applicability
    applies_to_sectors = models.JSONField(default=list, blank=True)
    applies_to_sizes = models.JSONField(default=list, blank=True)
    is_mandatory = models.BooleanField(default=True)

    # ---- Phase 2A: Knowledge-Base provenance (all optional, additive) ----
    # The legacy `framework` FK is intentionally left untouched; these new
    # fields let a control be traced to a versioned source without breaking it.
    framework_version = models.ForeignKey(
        'FrameworkVersion', on_delete=models.SET_NULL, null=True, blank=True, related_name='controls')
    source_document = models.ForeignKey(
        'SourceDocument', on_delete=models.SET_NULL, null=True, blank=True, related_name='controls')
    source_page = models.PositiveIntegerField(null=True, blank=True)
    source_reference = models.TextField(blank=True)
    external_reference = models.CharField(max_length=100, blank=True,
                                          help_text='e.g. NCA ECC 1-1-1, TPC-01, CT-01')
    is_legacy_import = models.BooleanField(default=False)
    import_notes = models.TextField(blank=True)

    class Meta:
        db_table = 'controls'
        # Phase 2D: identity moved to (framework_version, control_id) for official
        # controls so that, e.g., legacy NCA_ECC/1-1-1 (fv NULL) and official
        # NCA-ECC-2-2024/1-1-1 can coexist. Two partial constraints replace the
        # old unique_together: one guards official rows, one preserves the legacy
        # guarantee for fv-NULL rows.
        constraints = [
            models.UniqueConstraint(
                fields=['framework_version', 'control_id'],
                condition=models.Q(framework_version__isnull=False),
                name='uniq_official_control_per_framework_version'),
            models.UniqueConstraint(
                fields=['framework', 'control_id'],
                condition=models.Q(framework_version__isnull=True),
                name='uniq_legacy_control_per_framework'),
        ]

    def __str__(self):
        return f"{self.control_id}: {self.title[:60]}"


class CompanyControl(models.Model):
    """Tracks a company's compliance status for each applicable control."""
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('evidence_uploaded', 'Evidence Uploaded'),
        ('ai_reviewed', 'AI Reviewed'),
        ('compliant', 'Compliant'),
        ('non_compliant', 'Non-Compliant'),
        ('partially_compliant', 'Partially Compliant'),
        ('not_applicable', 'Not Applicable'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='company_controls')
    control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='company_controls')
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='not_started')
    ai_verdict = models.CharField(max_length=25, blank=True)
    ai_confidence = models.FloatField(default=0.0)
    ai_reasoning = models.TextField(blank=True)
    ai_reasoning_ar = models.TextField(blank=True)
    ai_recommendations = models.TextField(blank=True)
    ai_recommendations_ar = models.TextField(blank=True)
    auditor_verdict = models.CharField(max_length=25, blank=True)
    auditor_notes = models.TextField(blank=True)
    last_assessed = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'company_controls'
        unique_together = ['company', 'control']

    def __str__(self):
        return f"{self.company.name} - {self.control.control_id}: {self.status}"


class Evidence(models.Model):
    """Uploaded evidence document for a specific control."""
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('processing', 'Processing (OCR)'),
        ('ai_analyzing', 'AI Analyzing'),
        ('reviewed', 'AI Reviewed'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('needs_revision', 'Needs Revision'),
    ]

    company_control = models.ForeignKey(CompanyControl, on_delete=models.CASCADE, related_name='evidences')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    file = models.FileField(upload_to='evidence/%Y/%m/', storage=private_media_storage)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20)
    file_size = models.IntegerField(default=0)

    # OCR extracted text
    extracted_text = models.TextField(blank=True)
    ocr_confidence = models.FloatField(default=0.0)
    ocr_language = models.CharField(max_length=10, blank=True)

    # AI Analysis
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
    ai_analysis = models.JSONField(default=dict, blank=True)
    ai_verdict = models.CharField(max_length=25, blank=True)
    ai_reasoning = models.TextField(blank=True)
    ai_reasoning_ar = models.TextField(blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)
    analyzed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'evidences'

    def __str__(self):
        return f"{self.original_filename} ({self.status})"


class Assessment(models.Model):
    """Full compliance assessment/audit session for a company."""
    TYPE_CHOICES = [
        ('self_assessment', 'Self Assessment'),
        ('ai_assessment', 'AI Assessment'),
        ('formal_audit', 'Formal Audit'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('ai_complete', 'AI Review Complete'),
        ('auditor_review', 'Auditor Review'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
    ]

    # P0-02 — formal lifecycle. Terminal states are frozen (no re-open/edit/re-issue). The ONLY
    # product path that creates an Assessment does so directly in 'auditor_review'
    # (auditor_portal.ensure_assessments_for_auditor); 'draft'/'in_progress'/'ai_complete' are
    # legacy/unused states. This graph is MINIMAL and fail-closed: nothing may skip auditor
    # review to reach 'completed' — the legacy states can only advance forward to auditor_review.
    TERMINAL_STATES = frozenset({'completed', 'expired'})
    ALLOWED_TRANSITIONS = {
        'draft': frozenset({'auditor_review'}),
        'in_progress': frozenset({'auditor_review'}),
        'ai_complete': frozenset({'auditor_review'}),
        'auditor_review': frozenset({'completed', 'expired'}),   # the one real transition
        'completed': frozenset(),   # terminal — never re-opened or re-issued
        'expired': frozenset(),     # terminal
    }

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='assessments')
    assessment_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    frameworks = models.ManyToManyField(Framework, related_name='assessments')
    assigned_auditor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_assessments')

    overall_score = models.FloatField(default=0.0)
    nca_score = models.FloatField(default=0.0)
    aramco_score = models.FloatField(default=0.0)
    sabic_score = models.FloatField(default=0.0)

    total_controls = models.IntegerField(default=0)
    compliant_controls = models.IntegerField(default=0)
    non_compliant_controls = models.IntegerField(default=0)
    partially_compliant_controls = models.IntegerField(default=0)

    ai_summary = models.TextField(blank=True)
    ai_summary_ar = models.TextField(blank=True)
    auditor_report = models.TextField(blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'assessments'

    def __str__(self):
        return f"{self.company.name} - {self.assessment_type} ({self.status})"

    # ---- P0-02 formal state machine ----
    @property
    def is_locked(self):
        """A finalized/terminal assessment is frozen — it accepts no further audit edits
        (verdicts, findings, CAPA, notes, RFI) and its internal report cannot be re-issued."""
        return self.status in self.TERMINAL_STATES

    def can_transition_to(self, new_status):
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, frozenset())

    def transition_to(self, new_status, *, save=True, update_fields=None):
        """Move to `new_status`, refusing any illegal transition (raises InvalidAssessmentTransition).
        Same-state transitions are REJECTED too (no silent no-op) — a status is never in its own
        allowed set — so a re-issue attempt (completed -> completed) fails loudly. Callers that
        finalize should hold a DB lock (select_for_update) to stay race-safe."""
        if not self.can_transition_to(new_status):
            raise InvalidAssessmentTransition(
                f"Illegal assessment transition: {self.status!r} -> {new_status!r}")
        self.status = new_status
        if save:
            fields = list(update_fields) if update_fields else ['status']
            if 'status' not in fields:
                fields.append('status')
            self.save(update_fields=fields)


class ControlMapping(models.Model):
    """Cross-mapping between controls from different frameworks."""
    MAPPING_TYPE_CHOICES = [
        ('equivalent', 'Equivalent'),
        ('partial', 'Partial'),
        ('related', 'Related'),
    ]

    source_control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='source_mappings')
    target_control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='target_mappings')
    mapping_type = models.CharField(max_length=20, choices=MAPPING_TYPE_CHOICES, default='equivalent')
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'control_mappings'
        unique_together = ['source_control', 'target_control']

    def __str__(self):
        return f"{self.source_control.control_id} -> {self.target_control.control_id} ({self.mapping_type})"


# ============================================================
# Phase 1 — Source Registry + Framework Versioning (additive only)
# These models are added ALONGSIDE the existing schema. They do not alter or
# remove Framework.version, Control, CompanyControl, or Evidence. Controls are
# NOT linked to FrameworkVersion in Phase 1 (deferred to Phase 2).
# ============================================================

class SourceDocument(models.Model):
    """An official (or legacy) source document that controls are derived from.

    The authoritative source of truth for the control library — official
    PDFs/Word/templates/assessment tools — as opposed to the legacy bootstrap
    Excel. Used by Framework Versioning so every control can later be traced to
    a document + page (Phase 2)."""
    ISSUER_CHOICES = [
        ('NCA', 'National Cybersecurity Authority'),
        ('ARAMCO', 'Saudi Aramco'),
        ('SABIC', 'SABIC'),
        ('INTERNAL', 'Internal / CyberTrust KSA'),
        ('LEGACY', 'Legacy / Bootstrap'),
    ]
    DOCUMENT_TYPE_CHOICES = [
        ('standard', 'Standard'),
        ('guideline', 'Guideline'),
        ('template', 'Template'),
        ('assessment_tool', 'Assessment Tool'),
        ('policy_template', 'Policy Template'),
        ('procedure_template', 'Procedure Template'),
        ('bootstrap_excel', 'Bootstrap Excel'),
        ('srs', 'SRS / System Document'),
        ('other', 'Other'),
    ]
    LANGUAGE_CHOICES = [
        ('ar', 'Arabic'),
        ('en', 'English'),
        ('bilingual', 'Bilingual'),
        ('unknown', 'Unknown'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('superseded', 'Superseded'),
        ('draft', 'Draft'),
        ('legacy', 'Legacy'),
        ('unknown', 'Unknown'),
    ]

    title = models.CharField(max_length=300)
    issuer = models.CharField(max_length=20, choices=ISSUER_CHOICES)
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPE_CHOICES, default='other')
    version = models.CharField(max_length=50, blank=True)
    publication_date = models.DateField(null=True, blank=True)
    source_url = models.URLField(max_length=500, null=True, blank=True)
    local_path = models.CharField(max_length=500, null=True, blank=True)
    file_hash = models.CharField(max_length=128, null=True, blank=True, help_text='e.g. SHA-256')
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default='unknown')
    is_current = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unknown')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'source_documents'
        ordering = ['issuer', 'title', '-version']

    def __str__(self):
        v = f" {self.version}" if self.version else ''
        return f"[{self.issuer}] {self.title}{v}"


class FrameworkVersion(models.Model):
    """A specific, versioned edition of a framework (e.g. NCA-ECC-2-2024).

    Lets the platform distinguish ECC 2:2024 from ECC 2018, and treat the legacy
    334-control Excel as its own non-governing version. Phase 2 will link each
    Control to a FrameworkVersion; in Phase 1 the link is intentionally absent."""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('superseded', 'Superseded'),
        ('draft', 'Draft'),
        ('legacy', 'Legacy'),
    ]

    framework = models.ForeignKey(Framework, on_delete=models.CASCADE, related_name='versions')
    code = models.CharField(max_length=50, unique=True)
    version_label = models.CharField(max_length=100, blank=True)
    source_document = models.ForeignKey(
        SourceDocument, on_delete=models.SET_NULL, null=True, blank=True, related_name='framework_versions')
    effective_date = models.DateField(null=True, blank=True)
    retired_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    is_default = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # UAT-6: correct per-version display names. All NCA versions share one Framework row
    # (named after ECC), so framework.name is wrong for CCC/CSCC/TCC/OSMACC. Map by code.
    DISPLAY_NAMES = {
        'NCA-ECC-2-2024':      ('الضوابط الأساسية للأمن السيبراني', 'NCA Essential Cybersecurity Controls'),
        'NCA-ECC-2018':        ('الضوابط الأساسية للأمن السيبراني (2018)', 'NCA Essential Cybersecurity Controls (2018)'),
        'NCA-CCC-2-2024':      ('ضوابط الحوسبة السحابية', 'NCA Cloud Cybersecurity Controls'),
        'NCA-CSCC-1-2019':     ('ضوابط الأنظمة الحساسة', 'NCA Critical Systems Cybersecurity Controls'),
        'NCA-TCC-1-2021':      ('ضوابط العمل عن بُعد', 'NCA Telework Cybersecurity Controls'),
        'NCA-OSMACC-1-2021':   ('ضوابط حسابات التواصل الرسمية', 'NCA Official Social Media Accounts Cybersecurity Controls'),
        'NCA-OTCC-1-2022':     ('ضوابط التقنية التشغيلية', 'NCA Operational Technology Cybersecurity Controls'),
        'NCA-DCC-1-2022':      ('ضوابط حماية البيانات', 'NCA Data Cybersecurity Controls'),
        'ARAMCO-SACS-002':     ('معيار أرامكو SACS-002 للأطراف الثالثة', 'Saudi Aramco SACS-002'),
        'SABIC-CYBERTRUST-1-0': ('سابك سايبر ترست', 'SABIC CyberTrust'),
    }

    class Meta:
        db_table = 'framework_versions'
        ordering = ['framework', 'code']

    def __str__(self):
        return f"{self.code} ({self.get_status_display()})"

    @property
    def display_name_ar(self):
        pair = self.DISPLAY_NAMES.get(self.code)
        return pair[0] if pair else (self.version_label or (self.framework.name if self.framework_id else self.code))

    @property
    def display_name_en(self):
        pair = self.DISPLAY_NAMES.get(self.code)
        return pair[1] if pair else (self.version_label or (self.framework.name if self.framework_id else self.code))


class ControlVersion(models.Model):
    """Point-in-time snapshot of a control's text under a given framework version.

    Lets the platform keep history when a control's wording changes across
    editions (e.g. ECC 2018 -> ECC 2:2024) without mutating the live Control.
    Additive only — no existing model depends on it."""
    control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='versions')
    framework_version = models.ForeignKey(
        FrameworkVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name='control_versions')
    source_document = models.ForeignKey(
        SourceDocument, on_delete=models.SET_NULL, null=True, blank=True, related_name='control_versions')
    version_label = models.CharField(max_length=100)
    control_id_snapshot = models.CharField(max_length=50, blank=True)
    title_snapshot = models.CharField(max_length=500, blank=True)
    statement_snapshot = models.TextField(blank=True)
    effective_date = models.DateField(null=True, blank=True)
    retired_date = models.DateField(null=True, blank=True)
    change_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'control_versions'
        ordering = ['control', '-effective_date', 'version_label']

    def __str__(self):
        return f"{self.control.control_id} @ {self.version_label}"


class ControlApplicabilityTag(models.Model):
    """A tag describing when a control applies (e.g. cloud, ot_ics, supplier).

    Drives later applicability logic (Phase 4). Phase 2A only defines the model;
    tags are populated by official import / rules engine in later phases."""
    SOURCE_CHOICES = [
        ('manual', 'Manual'),
        ('official', 'Official'),
        ('inferred', 'Inferred'),
        ('legacy_excel', 'Legacy Excel'),
    ]

    control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='applicability_tags')
    tag = models.CharField(max_length=50)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='manual')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'control_applicability_tags'
        ordering = ['control', 'tag']
        constraints = [
            models.UniqueConstraint(fields=['control', 'tag'], name='uniq_control_tag'),
        ]

    def __str__(self):
        return f"{self.control.control_id} :: {self.tag} ({self.source})"


# ============================================================
# Phase 3A — Company Intake + Framework Applicability (additive only)
# Foundation that moves framework selection from manual target_* checkboxes
# toward a structured, explainable, rule-based applicability model. No evidence
# / CompanyControl / upload changes here.
# ============================================================

class CompanyIntakeProfile(models.Model):
    """Structured intake answers for a company, used to compute framework applicability."""
    REVIEW_STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('completed', 'Completed'),
        ('reviewed', 'Reviewed'),
    ]
    SABIC_SUPPLIER_TYPES = [
        ('NC', 'Network Connectivity'),
        ('CCS', 'Cloud Computing Services'),
        ('OMS', 'Outsourcing and Managed Services'),
        ('CS', 'Consultancy Services'),
        ('SM', 'Software Management'),
        ('OT', 'OT/ICS Products and Services'),
    ]

    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='intake_profile')
    sector = models.CharField(max_length=50, blank=True)

    # Boolean intake signals (all optional, default False).
    is_government_entity = models.BooleanField(default=False)
    is_critical_system_operator = models.BooleanField(default=False)
    uses_cloud_services = models.BooleanField(default=False)
    provides_cloud_services = models.BooleanField(default=False)
    handles_sensitive_data = models.BooleanField(default=False)
    handles_personal_data = models.BooleanField(default=False)
    has_ot_environment = models.BooleanField(default=False)
    has_remote_work = models.BooleanField(default=False)
    manages_official_social_media_accounts = models.BooleanField(default=False)
    works_with_aramco = models.BooleanField(default=False)
    works_with_sabic = models.BooleanField(default=False)

    aramco_supplier_type = models.CharField(max_length=50, blank=True)
    sabic_supplier_type = models.CharField(max_length=10, choices=SABIC_SUPPLIER_TYPES, blank=True)

    requested_frameworks = models.JSONField(default=list, blank=True)

    review_status = models.CharField(max_length=20, choices=REVIEW_STATUS_CHOICES, default='draft')
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_intake_profiles')
    notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'company_intake_profiles'

    def __str__(self):
        return f"Intake[{self.company.name}] ({self.review_status})"


class FrameworkApplicabilityResult(models.Model):
    """A deterministic, explainable applicability decision for one company + framework version."""
    DECISION_CHOICES = [
        ('applicable', 'Applicable'),
        ('not_applicable', 'Not Applicable'),
        ('needs_review', 'Needs Review'),
        ('manually_overridden', 'Manually Overridden'),
    ]
    SOURCE_CHOICES = [
        ('rule', 'Rule Engine'),
        ('manual', 'Manual'),
        ('legacy_checkbox', 'Legacy Checkbox'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='applicability_results')
    framework_version = models.ForeignKey(
        FrameworkVersion, on_delete=models.CASCADE, related_name='applicability_results')
    decision = models.CharField(max_length=25, choices=DECISION_CHOICES)
    reason = models.TextField(blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='rule')
    confidence = models.FloatField(default=1.0)
    overridden_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='overridden_applicability_results')
    override_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'framework_applicability_results'
        unique_together = ['company', 'framework_version']
        ordering = ['company', 'framework_version']

    def __str__(self):
        return f"{self.company.name} :: {self.framework_version.code} = {self.decision}"


# ============================================================
# Phase 3C — Framework Approval (scope) + Control Applicability planning (additive)
# Approval/planning layer AFTER applicability and BEFORE evidence checklist.
# Distinct from legacy CompanyControl (which must NOT be generated here).
# ============================================================

class CompanyFrameworkScope(models.Model):
    """Reviewed/approved inclusion of a framework version for a company."""
    STATUS_CHOICES = [
        ('proposed', 'Proposed'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('needs_review', 'Needs Review'),
    ]
    SOURCE_CHOICES = [
        ('applicability_result', 'Applicability Result'),
        ('manual', 'Manual'),
        ('legacy_checkbox', 'Legacy Checkbox'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='framework_scopes')
    framework_version = models.ForeignKey(
        FrameworkVersion, on_delete=models.CASCADE, related_name='company_scopes')
    applicability_result = models.ForeignKey(
        'FrameworkApplicabilityResult', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scopes')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='proposed')
    source = models.CharField(max_length=25, choices=SOURCE_CHOICES, default='applicability_result')
    reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_scopes')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='rejected_scopes')
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'company_framework_scopes'
        unique_together = ['company', 'framework_version']
        ordering = ['company', 'framework_version']

    def __str__(self):
        return f"{self.company.name} :: {self.framework_version.code} = {self.status}"


class ControlApplicabilityResult(models.Model):
    """Planned (NOT checklist) applicability of an official control under an approved framework scope."""
    DECISION_CHOICES = [
        ('applicable', 'Applicable'),
        ('not_applicable', 'Not Applicable'),
        ('needs_review', 'Needs Review'),
        ('manually_overridden', 'Manually Overridden'),
    ]
    SOURCE_CHOICES = [
        ('framework_scope', 'Framework Scope'),
        ('rule', 'Rule'),
        ('manual', 'Manual'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='control_applicability')
    framework_scope = models.ForeignKey(
        CompanyFrameworkScope, on_delete=models.CASCADE, related_name='control_results')
    control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='applicability_results')
    decision = models.CharField(max_length=25, choices=DECISION_CHOICES, default='applicable')
    reason = models.TextField(blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='framework_scope')
    confidence = models.FloatField(default=1.0)
    overridden_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='overridden_control_results')
    override_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'control_applicability_results'
        unique_together = ['company', 'control']
        ordering = ['company', 'control']

    def __str__(self):
        return f"{self.company.name} :: {self.control.control_id} = {self.decision}"


# ============================================================
# Phase 3D — Evidence Requirement templates + company checklist planning (additive)
# EvidenceRequirement = reusable template per control. EvidenceChecklistItem =
# a company-specific PLANNED task. NOT Evidence, NOT CompanyControl, NO upload here.
# Official controls only.
# ============================================================

class EvidenceRequirement(models.Model):
    """Reusable template describing an evidence item expected for a control."""
    EVIDENCE_TYPE_CHOICES = Control.EVIDENCE_TYPE_CHOICES
    REQUIREMENT_LEVEL_CHOICES = [
        ('mandatory', 'Mandatory'),
        ('recommended', 'Recommended'),
        ('optional', 'Optional'),
    ]
    SOURCE_CHOICES = [
        ('default_template', 'Default Template'),
        ('official', 'Official Source'),
        ('manual', 'Manual'),
    ]

    control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='evidence_requirements')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    evidence_type = models.CharField(max_length=20, choices=EVIDENCE_TYPE_CHOICES, default='policy')
    requirement_level = models.CharField(max_length=20, choices=REQUIREMENT_LEVEL_CHOICES, default='mandatory')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='default_template')
    source_reference = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'evidence_requirements'
        ordering = ['control', 'sort_order']
        unique_together = ['control', 'title']

    def __str__(self):
        return f"{self.control.control_id} :: {self.title}"


class EvidenceChecklistItem(models.Model):
    """A company-specific planned evidence task (NOT an uploaded Evidence record)."""
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('waived', 'Waived'),
    ]
    PRIORITY_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='evidence_checklist_items')
    control_applicability_result = models.ForeignKey(
        ControlApplicabilityResult, on_delete=models.CASCADE, related_name='checklist_items')
    evidence_requirement = models.ForeignKey(
        EvidenceRequirement, on_delete=models.CASCADE, related_name='checklist_items')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    due_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_checklist_items')
    notes = models.TextField(blank=True)
    waiver_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'evidence_checklist_items'
        unique_together = ['company', 'evidence_requirement']
        ordering = ['company', 'control_applicability_result']

    def __str__(self):
        return f"{self.company.name} :: {self.evidence_requirement.title} ({self.status})"


# ============================================================
# Phase 3E — Evidence Upload v2: EvidenceSubmission linked to checklist items (additive)
# New upload model. Does NOT replace the legacy Evidence model, does NOT write
# CompanyControl, does NOT make compliance decisions, no AI/OCR here.
# ============================================================

class EvidenceSubmission(models.Model):
    """An uploaded evidence file linked to an EvidenceChecklistItem (upload v2)."""
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('pending_review', 'Pending Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('needs_reupload', 'Needs Re-upload'),
        ('archived', 'Archived'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='evidence_submissions')
    checklist_item = models.ForeignKey(
        EvidenceChecklistItem, on_delete=models.CASCADE, related_name='submissions')
    uploaded_file = models.FileField(upload_to='evidence_v2/%Y/%m/', storage=private_media_storage)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20)
    file_size = models.PositiveIntegerField(default=0)
    file_hash = models.CharField(max_length=128, blank=True, help_text='SHA-256 of the uploaded file')
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_review')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='evidence_submissions')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'evidence_submissions'
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['company', '-uploaded_at']),   # DD: tenant list + default order
            models.Index(fields=['company', 'status']),         # DD: status filters at scale
        ]

    def __str__(self):
        return f"{self.company.name} :: {self.original_filename} (v{self.version}, {self.status})"


# ============================================================
# Phase 3F — Advisory AI/OCR evidence analysis (additive)
# DRAFT analysis only. NOT a compliance decision, NOT an auditor review,
# NOT a ControlAssessment. AI is assistant only; final decision is the auditor's (Phase 3G).
# ============================================================

class EvidenceAnalysisResult(models.Model):
    """Advisory analysis of an EvidenceSubmission. One latest result per submission."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
        ('needs_human_review', 'Needs Human Review'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='evidence_analyses')
    evidence_submission = models.OneToOneField(
        EvidenceSubmission, on_delete=models.CASCADE, related_name='analysis')
    checklist_item = models.ForeignKey(
        EvidenceChecklistItem, on_delete=models.CASCADE, related_name='analyses')
    control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='evidence_analyses')
    evidence_requirement = models.ForeignKey(
        EvidenceRequirement, on_delete=models.SET_NULL, null=True, blank=True, related_name='analyses')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    extracted_text = models.TextField(blank=True)
    extracted_text_truncated = models.BooleanField(default=False)
    summary = models.TextField(blank=True)
    requirement_match = models.TextField(blank=True)
    potential_gaps = models.TextField(blank=True)
    risk_flags = models.JSONField(default=list, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    model_used = models.CharField(max_length=80, blank=True)
    provider = models.CharField(max_length=40, blank=True)
    prompt_version = models.CharField(max_length=20, blank=True)
    analysis_metadata = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_analyses')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'evidence_analysis_results'
        ordering = ['-created_at']

    def __str__(self):
        return f"Analysis[{self.evidence_submission.original_filename}] ({self.status})"


# ============================================================
# Phase 3G — Auditor-driven Control Assessment (additive)
# First FINAL assessment model. Created/updated by auditor/staff ONLY — never by
# AI, never by evidence upload/analysis. Official controls only. Not CompanyControl.
# ============================================================

class ControlAssessment(models.Model):
    """The auditor's final compliance decision for an official control (per company)."""
    STATUS_CHOICES = [
        ('not_reviewed', 'Not Reviewed'),
        ('compliant', 'Compliant'),
        ('partially_compliant', 'Partially Compliant'),
        ('non_compliant', 'Non-Compliant'),
        ('not_applicable', 'Not Applicable'),
        ('needs_more_evidence', 'Needs More Evidence'),
    ]
    RISK_LEVEL_CHOICES = [('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')]
    CONFIDENCE_CHOICES = [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='control_assessments')
    control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='assessments')
    control_applicability_result = models.ForeignKey(
        ControlApplicabilityResult, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assessments')
    framework_scope = models.ForeignKey(
        CompanyFrameworkScope, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assessments')

    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='not_reviewed')
    score = models.IntegerField(null=True, blank=True)
    auditor_notes = models.TextField(blank=True)
    remediation_required = models.BooleanField(default=False)
    remediation_plan = models.TextField(blank=True)
    remediation_due_date = models.DateField(null=True, blank=True)
    evidence_summary = models.TextField(blank=True)
    ai_summary_snapshot = models.TextField(blank=True)
    risk_level = models.CharField(max_length=10, choices=RISK_LEVEL_CHOICES, blank=True)
    confidence_level = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='control_assessments')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'control_assessments'
        unique_together = ['company', 'control']
        ordering = ['company', 'control']

    def __str__(self):
        return f"{self.company.name} :: {self.control.control_id} = {self.status}"


class EvidenceTextExtraction(models.Model):
    """Phase 6C-FIX-A — persisted result of a safe, read-only text-extraction
    attempt for one EvidenceSubmission.

    Makes the journey "text extraction" step truthful: it is only "completed"
    when an actual successful extraction (status='extracted', char_count>0) has
    been recorded. Stores no compliance/sufficiency judgment — extraction only.
    """
    STATUS_CHOICES = [
        ('extracted', 'Extracted'),
        ('no_text_extracted', 'No Text Extracted'),
        ('unsupported_type', 'Unsupported Type'),
        ('too_large', 'Too Large'),
        ('failed', 'Failed'),
    ]
    submission = models.OneToOneField(
        'compliance.EvidenceSubmission', on_delete=models.CASCADE, related_name='text_extraction')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    extracted_text = models.TextField(blank=True)
    char_count = models.PositiveIntegerField(default=0)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    extraction_method = models.CharField(max_length=64, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)
    truncated = models.BooleanField(default=False)
    extracted_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'evidence_text_extractions'

    STATUS_AR = {
        'extracted': 'تم الاستخراج',
        'no_text_extracted': 'تعذّر استخراج نص كافٍ',
        'unsupported_type': 'نوع ملف غير مدعوم',
        'too_large': 'الملف كبير جدًا',
        'failed': 'فشل الاستخراج',
    }

    def __str__(self):
        return f"Extraction[{self.submission_id}] = {self.status}"

    @property
    def has_text(self):
        return self.status == 'extracted' and self.char_count > 0

    @property
    def status_ar(self):
        return self.STATUS_AR.get(self.status, self.status)


class EvidenceAIAnalysis(models.Model):
    """Phase 6D — advisory AI analysis of an EvidenceSubmission's EXTRACTED text.

    Advisory only: it helps a human auditor and never decides compliance. It is
    gated on a successful EvidenceTextExtraction, stores no C/PC/NC or final
    verdict, and never touches ControlAssessment / CompanyControl / reports.
    Distinct from the legacy Phase 3F EvidenceAnalysisResult.
    """
    STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('skipped', 'Skipped'),
        ('failed', 'Failed'),
    ]
    RELEVANCE_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
        ('unclear', 'Unclear'),
    ]
    submission = models.OneToOneField(
        'compliance.EvidenceSubmission', on_delete=models.CASCADE, related_name='ai_analysis')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    relevance = models.CharField(max_length=32, choices=RELEVANCE_CHOICES, blank=True)
    confidence = models.PositiveSmallIntegerField(default=0)
    summary = models.TextField(blank=True)
    matched_signals = models.JSONField(default=list, blank=True)
    missing_items = models.JSONField(default=list, blank=True)
    recommendations = models.JSONField(default=list, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    analyzed_at = models.DateTimeField(auto_now=True)

    STATUS_AR = {'completed': 'مكتمل', 'skipped': 'متخطّى', 'failed': 'فشل'}
    RELEVANCE_AR = {'high': 'مرتفع', 'medium': 'متوسط', 'low': 'منخفض', 'unclear': 'غير واضح'}

    class Meta:
        db_table = 'evidence_ai_analyses'

    def __str__(self):
        return f"AIAnalysis[{self.submission_id}] = {self.status}/{self.relevance}"

    @property
    def status_ar(self):
        return self.STATUS_AR.get(self.status, self.status)

    @property
    def relevance_ar(self):
        return self.RELEVANCE_AR.get(self.relevance, self.relevance)


class EvidenceRuleEvaluation(models.Model):
    """Phase 6E — deterministic, SYSTEM-SUGGESTED (non-final) compliance status for
    one EvidenceSubmission.

    A suggestion only — it combines applicability + extraction + advisory AI signals
    via simple deterministic rules. It is NEVER a final decision, auditor verdict, or
    certification, and it never writes ControlAssessment / CompanyControl / reports.
    """
    STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('skipped', 'Skipped'),
        ('failed', 'Failed'),
    ]
    submission = models.OneToOneField(
        'compliance.EvidenceSubmission', on_delete=models.CASCADE, related_name='rule_evaluation')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    suggested_status = models.CharField(max_length=64, blank=True)
    confidence = models.PositiveSmallIntegerField(default=0)
    rationale = models.TextField(blank=True)
    rule_signals = models.JSONField(default=list, blank=True)
    missing_requirements = models.JSONField(default=list, blank=True)
    framework_type = models.CharField(max_length=32, blank=True)
    error_message = models.TextField(blank=True)
    evaluated_at = models.DateTimeField(auto_now=True)

    # Suggested-status display labels (ALWAYS advisory — "بانتظار مراجعة المدقق").
    SUGGESTED_AR = {
        'suggested_c': 'متوافق مبدئيًا',
        'suggested_pc': 'متوافق جزئيًا مبدئيًا',
        'suggested_nc': 'غير متوافق مبدئيًا',
        'suggested_na': 'غير منطبق مبدئيًا',
        'suggested_compliance': 'امتثال مبدئي',
        'suggested_noncompliance': 'عدم امتثال مبدئي',
        'suggested_not_applicable': 'غير منطبق مبدئيًا',
        'needs_review': 'يحتاج مراجعة',
        'insufficient_data': 'بيانات غير كافية',
    }
    STATUS_AR = {'completed': 'مكتمل', 'skipped': 'متخطّى', 'failed': 'فشل'}

    class Meta:
        db_table = 'evidence_rule_evaluations'

    def __str__(self):
        return f"RuleEval[{self.submission_id}] = {self.suggested_status}"

    @property
    def suggested_status_ar(self):
        return self.SUGGESTED_AR.get(self.suggested_status, self.suggested_status)

    @property
    def status_ar(self):
        return self.STATUS_AR.get(self.status, self.status)


class AuditorFinalVerdict(models.Model):
    """Phase 6F — a HUMAN reviewer's final verdict for one EvidenceSubmission.

    The first human-reviewed final decision recorded inside the platform. It is an
    INTERNAL review decision — NOT an official certification/accreditation. It never
    issues a certificate, never finalizes external reports, and never bulk-creates
    CompanyControl. Recorded only by staff/superuser or an assigned active auditor.
    """
    STATUS_CHOICES = [
        # NCA-style
        ('final_c', 'Final Compliant'),
        ('final_pc', 'Final Partially Compliant'),
        ('final_nc', 'Final Non-Compliant'),
        ('final_na', 'Final Not Applicable'),
        # Aramco / SABIC-style
        ('final_compliance', 'Final Compliance'),
        ('final_noncompliance', 'Final Non-Compliance'),
        ('final_not_applicable', 'Final Not Applicable'),
        # shared
        ('needs_more_evidence', 'Needs More Evidence'),
    ]
    submission = models.OneToOneField(
        'compliance.EvidenceSubmission', on_delete=models.CASCADE, related_name='auditor_final_verdict')
    reviewer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='auditor_final_verdicts')
    status = models.CharField(max_length=64, choices=STATUS_CHOICES)
    confidence = models.PositiveSmallIntegerField(default=0)
    rationale = models.TextField()
    required_actions = models.JSONField(default=list, blank=True)
    framework_type = models.CharField(max_length=32, blank=True)
    source_rule_evaluation = models.ForeignKey(
        'compliance.EvidenceRuleEvaluation', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='auditor_verdicts')
    reviewed_at = models.DateTimeField(auto_now=True)

    STATUS_AR = {
        'final_c': 'متوافق (بعد مراجعة المدقق)',
        'final_pc': 'متوافق جزئيًا (بعد مراجعة المدقق)',
        'final_nc': 'غير متوافق (بعد مراجعة المدقق)',
        'final_na': 'غير منطبق (بعد مراجعة المدقق)',
        'final_compliance': 'امتثال (بعد مراجعة المدقق)',
        'final_noncompliance': 'عدم امتثال (بعد مراجعة المدقق)',
        'final_not_applicable': 'غير منطبق (بعد مراجعة المدقق)',
        'needs_more_evidence': 'بحاجة إلى أدلة إضافية',
    }

    class Meta:
        db_table = 'auditor_final_verdicts'

    def __str__(self):
        return f"Verdict[{self.submission_id}] = {self.status} by {self.reviewer_id}"

    @property
    def status_ar(self):
        return self.STATUS_AR.get(self.status, self.status)

    @property
    def is_stale(self):
        """F-AUDIT R2: True when a NEWER evidence version exists for the same checklist
        item than the one this verdict reviewed — i.e. the verdict is on outdated evidence
        and needs re-review. Derived read-only (no persisted flag / no migration): the
        verdict is bound OneToOne to a specific submission, so "stale" == "a sibling
        submission with a higher version exists for this submission's checklist_item".
        A submission with no checklist_item (legacy/orphan) is never considered stale."""
        item_id = self.submission.checklist_item_id
        if not item_id:
            return False
        return EvidenceSubmission.objects.filter(
            checklist_item_id=item_id, version__gt=self.submission.version).exists()


class ControlGapAssessment(models.Model):
    """Phase 8F — deterministic, evidence-aware INTERNAL readiness per control.

    A preliminary, system-calculated readiness status for one applicable official
    control (per company). It is NOT the auditor's final decision (ControlAssessment)
    and NOT an official certification/accreditation — it is an evidence-based
    preliminary status that always requires human review. Recomputed deterministically
    from existing data (applicability scope, evidence submissions, text extraction,
    and the auditor assessment when present). No AI, no external calls.
    """
    STATUS_CHOICES = [
        ('compliant', 'Compliant'),
        ('partially_compliant', 'Partially Compliant'),
        ('missing', 'Missing'),
        ('not_applicable', 'Not Applicable'),
        ('needs_review', 'Needs Review'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='control_gap_assessments')
    framework_version = models.ForeignKey(
        FrameworkVersion, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='control_gap_assessments')
    control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='gap_assessments')

    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='needs_review')
    score = models.PositiveSmallIntegerField(default=0)  # 0-100 preliminary readiness
    evidence_count = models.PositiveIntegerField(default=0)
    extracted_text_available_count = models.PositiveIntegerField(default=0)
    reason = models.TextField(blank=True)
    calculated_by = models.CharField(max_length=64, default='deterministic_v1')
    calculated_at = models.DateTimeField(auto_now=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_gap_assessments')
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'control_gap_assessments'
        unique_together = ['company', 'control']
        ordering = ['company', 'control']

    def __str__(self):
        return f"Gap[{self.company_id}/{self.control_id}] = {self.status}"
