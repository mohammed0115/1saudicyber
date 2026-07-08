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
            'aramco_supplier_type': 'تصنيف المورّد لدى أرامكو (اختياري)',
            'works_with_sabic': 'مورّد / تتعامل مع سابك',
            'sabic_supplier_type': 'فئة المورّد لدى سابك (اختياري)',
            'notes': 'ملاحظات',
        }
        help_texts = {
            'uses_cloud_services': ('استخدام خدمات سحابية/SaaS/API خارجية مثل الاستضافة، VPS، '
                                    'OpenAI API، التخزين السحابي، البريد السحابي، قواعد البيانات السحابية.'),
            'provides_cloud_services': 'تقديم منصّة SaaS/سحابية للعملاء (وليس مجرّد استخدامها).',
            'is_critical_system_operator': 'الأنظمة التي يؤثّر تعطّلها على الخدمات الوطنية/الحيوية.',
            'aramco_supplier_type': 'حدّد تصنيف المورّد لدى أرامكو إن كان معروفًا (اختياري).',
            'sabic_supplier_type': 'اختر فئة المورّد لدى سابك إن كانت معروفة (اختياري).',
        }
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    # UAT-5: bilingual SABIC supplier-category options for the Arabic UI.
    SABIC_BILINGUAL_CHOICES = [
        ('', '— اختر (اختياري) —'),
        ('NC', 'اتصال الشبكات / Network Connectivity'),
        ('CCS', 'خدمات الحوسبة السحابية / Cloud Computing Services'),
        ('OMS', 'الإسناد والخدمات المُدارة / Outsourcing and Managed Services'),
        ('CS', 'الخدمات الاستشارية / Consultancy Services'),
        ('SM', 'إدارة البرمجيات / Software Management'),
        ('OT', 'منتجات وخدمات OT/ICS / OT/ICS Products and Services'),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'sabic_supplier_type' in self.fields:
            self.fields['sabic_supplier_type'].choices = self.SABIC_BILINGUAL_CHOICES
            self.fields['sabic_supplier_type'].required = False
        if 'aramco_supplier_type' in self.fields:
            self.fields['aramco_supplier_type'].required = False
        # UAT: give the non-checkbox inputs (selects / text / textarea) a visible, consistent
        # bordered style. Previously they inherited the checkbox row layout and rendered as bare
        # inline controls (invisible textarea, split select).
        field_css = ('w-full border border-gov-gray-300 rounded-lg px-3 py-2 text-sm '
                     'text-gov-gray-800 bg-white focus:outline-none focus:ring-2 '
                     'focus:ring-gov-green-500 focus:border-gov-green-500')
        for name in ('aramco_supplier_type', 'sabic_supplier_type', 'notes'):
            if name in self.fields:
                self.fields[name].widget.attrs['class'] = field_css
        if 'notes' in self.fields:
            self.fields['notes'].widget.attrs.update({
                'rows': 4,
                'style': 'min-height:100px;',
                'placeholder': 'اكتب أي ملاحظات إضافية حول نطاق التصنيف...',
            })

    def clean(self):
        # UAT-2/3: a supplier category is meaningful only when its supplier checkbox is set.
        # If the checkbox is unchecked, clear any stale/hidden dropdown value so it can never
        # influence framework proposal on the backend (defence beyond the frontend JS).
        cleaned = super().clean()
        if not cleaned.get('works_with_aramco'):
            cleaned['aramco_supplier_type'] = ''
        if not cleaned.get('works_with_sabic'):
            cleaned['sabic_supplier_type'] = ''
        return cleaned


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
