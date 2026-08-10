"""DRF serializers for the CyberTrust KSA REST API (/api/v1)."""
from rest_framework import serializers

from core.models import Company
from compliance.models import (
    Control, CompanyControl, Evidence, ControlAssessment, EvidenceSubmission,
)
from monitoring.models import ComplianceScore, Alert
from ai_engine.models import GapAnalysis


class CompanySerializer(serializers.ModelSerializer):
    applicable_frameworks = serializers.ReadOnlyField()

    class Meta:
        model = Company
        fields = ['id', 'name', 'name_ar', 'cr_number', 'sector', 'size', 'status',
                  'risk_level', 'overall_compliance_score', 'nca_score', 'aramco_score',
                  'sabic_score', 'applicable_frameworks']


class ControlSerializer(serializers.ModelSerializer):
    framework = serializers.CharField(source='framework.code', read_only=True)
    domain = serializers.CharField(source='domain.name', read_only=True)

    class Meta:
        model = Control
        fields = ['id', 'control_id', 'title', 'title_ar', 'description', 'priority',
                  'evidence_type', 'evidence_guidance', 'evidence_guidance_ar',
                  'framework', 'domain', 'is_mandatory']


class CompanyControlSerializer(serializers.ModelSerializer):
    control = ControlSerializer(read_only=True)

    class Meta:
        model = CompanyControl
        fields = ['id', 'status', 'ai_verdict', 'ai_confidence', 'ai_reasoning',
                  'ai_reasoning_ar', 'last_assessed', 'control']


class EvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evidence
        fields = ['id', 'original_filename', 'file_type', 'file_size', 'status',
                  'ai_verdict', 'ocr_confidence', 'uploaded_at', 'analyzed_at']
        read_only_fields = fields


class ControlAssessmentSerializer(serializers.ModelSerializer):
    """Phase 3G — the auditor's FINAL compliance decision per official control.
    Modern replacement for the legacy CompanyControl view."""
    control_code = serializers.CharField(source='control.control_id', read_only=True)
    control_title = serializers.CharField(source='control.title', read_only=True)
    framework = serializers.CharField(source='control.framework.code', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ControlAssessment
        fields = ['id', 'control_code', 'control_title', 'framework', 'status', 'status_display',
                  'score', 'risk_level', 'confidence_level', 'remediation_required',
                  'remediation_due_date', 'reviewed_at', 'updated_at']
        read_only_fields = fields


class EvidenceSubmissionSerializer(serializers.ModelSerializer):
    """Upload-v2 evidence (modern replacement for the legacy Evidence view)."""
    class Meta:
        model = EvidenceSubmission
        fields = ['id', 'original_filename', 'file_type', 'file_size', 'file_hash',
                  'version', 'status', 'uploaded_at', 'notes']
        read_only_fields = fields


class ComplianceScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceScore
        fields = ['date', 'overall_score', 'nca_score', 'aramco_score', 'sabic_score',
                  'controls_compliant', 'controls_total']


class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = ['id', 'alert_type', 'severity', 'title', 'title_ar', 'description',
                  'affected_control', 'is_resolved', 'created_at']


class GapAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = GapAnalysis
        fields = ['framework_code', 'total_controls', 'compliant_count', 'non_compliant_count',
                  'partially_compliant_count', 'not_assessed_count', 'compliance_score',
                  'risk_score', 'high_risk_gaps', 'remediation_priorities', 'generated_at']


class RegisterSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=255)
    company_name_ar = serializers.CharField(max_length=255, required=False, allow_blank=True)
    cr_number = serializers.CharField(max_length=20)
    sector = serializers.ChoiceField(choices=Company.SECTOR_CHOICES)
    size = serializers.ChoiceField(choices=Company.SIZE_CHOICES)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=12, write_only=True)
    first_name = serializers.CharField(max_length=30)
    last_name = serializers.CharField(max_length=30)
    target_nca = serializers.BooleanField(required=False, default=False)
    target_aramco = serializers.BooleanField(required=False, default=False)
    target_sabic = serializers.BooleanField(required=False, default=False)

    def validate_cr_number(self, value):
        value = value.strip()
        if not value.isdigit() or len(value) != 10:
            raise serializers.ValidationError('CR number must be exactly 10 digits.')
        if Company.objects.filter(cr_number=value).exists():
            raise serializers.ValidationError('This CR number is already registered.')
        return value

    def validate(self, data):
        if not (data.get('target_nca') or data.get('target_aramco') or data.get('target_sabic')):
            raise serializers.ValidationError('Select at least one certification target.')
        return data
