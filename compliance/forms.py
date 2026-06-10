"""Phase 3B — Company Intake form (business intake data, not system config)."""
from django import forms

from .models import CompanyIntakeProfile


class CompanyIntakeForm(forms.ModelForm):
    """Structured intake answers used to compute framework applicability."""

    class Meta:
        model = CompanyIntakeProfile
        fields = [
            'is_government_entity', 'is_critical_system_operator',
            'uses_cloud_services', 'provides_cloud_services',
            'handles_sensitive_data', 'handles_personal_data',
            'has_ot_environment', 'has_remote_work',
            'manages_official_social_media_accounts',
            'works_with_aramco', 'aramco_supplier_type',
            'works_with_sabic', 'sabic_supplier_type',
            'notes',
        ]
        labels = {
            'is_government_entity': 'جهة حكومية أو تابعة لجهة حكومية',
            'is_critical_system_operator': 'تشغّل أو تستضيف أنظمة حساسة / بنية وطنية حرجة',
            'uses_cloud_services': 'تستخدم خدمات سحابية خارجية',
            'provides_cloud_services': 'تقدّم خدمة سحابية للعملاء',
            'handles_sensitive_data': 'تعالج بيانات حساسة أو مصنّفة',
            'handles_personal_data': 'تعالج بيانات شخصية',
            'has_ot_environment': 'لديها بيئة OT/ICS أو أنظمة صناعية',
            'has_remote_work': 'تسمح بالعمل عن بُعد',
            'manages_official_social_media_accounts': 'تدير حسابات تواصل اجتماعي رسمية',
            'works_with_aramco': 'مورّد / تتعامل مع أرامكو السعودية',
            'aramco_supplier_type': 'تصنيف المورّد لدى أرامكو (إن وُجد)',
            'works_with_sabic': 'مورّد / تتعامل مع سابك',
            'sabic_supplier_type': 'فئة المورّد لدى سابك',
            'notes': 'ملاحظات',
        }
        help_texts = {
            'uses_cloud_services': ('استخدام خدمات سحابية/SaaS/API خارجية مثل الاستضافة، VPS، '
                                    'OpenAI API، التخزين السحابي، البريد السحابي، قواعد البيانات السحابية.'),
            'provides_cloud_services': 'تقديم منصّة SaaS/سحابية للعملاء (وليس مجرّد استخدامها).',
            'is_critical_system_operator': 'الأنظمة التي يؤثّر تعطّلها على الخدمات الوطنية/الحيوية.',
        }
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


# ============================================================
# Phase 3E — Evidence Upload v2 form
# ============================================================
from django.conf import settings as _settings

# Allowed extensions for upload v2 (per Phase 3E spec).
EVIDENCE_V2_ALLOWED_EXTENSIONS = ['pdf', 'png', 'jpg', 'jpeg', 'xlsx', 'docx', 'csv', 'txt']
# Reuse the existing project limit if present, else a conservative 50 MB default.
EVIDENCE_V2_MAX_SIZE = getattr(_settings, 'MAX_EVIDENCE_FILE_SIZE', 50 * 1024 * 1024)


class EvidenceSubmissionForm(forms.Form):
    """Upload v2: validates file type/size only. No AI/OCR, no content parsing."""
    uploaded_file = forms.FileField()
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)

    def clean_uploaded_file(self):
        import os
        f = self.cleaned_data['uploaded_file']
        ext = os.path.splitext(f.name)[1].lower().lstrip('.')
        if ext not in EVIDENCE_V2_ALLOWED_EXTENSIONS:
            raise forms.ValidationError(
                f'نوع الملف ".{ext}" غير مسموح. المسموح: {", ".join(EVIDENCE_V2_ALLOWED_EXTENSIONS)}.')
        if f.size > EVIDENCE_V2_MAX_SIZE:
            raise forms.ValidationError(
                f'حجم الملف كبير جداً ({f.size // (1024*1024)} MB). الحد الأقصى '
                f'{EVIDENCE_V2_MAX_SIZE // (1024*1024)} MB.')
        return f
