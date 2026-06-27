from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Company


# Phase 8C — Arabic display labels for registration choices. Values are IDENTICAL
# to Company.SECTOR_CHOICES / SIZE_CHOICES (logic unchanged); only labels are Arabic,
# applied at the form/view layer so no model change / migration is needed.
SECTOR_CHOICES_AR = [
    ('oil_gas', 'النفط والغاز'),
    ('petrochemical', 'البتروكيماويات'),
    ('banking', 'البنوك والتمويل'),
    ('telecom', 'الاتصالات'),
    ('healthcare', 'الرعاية الصحية'),
    ('government', 'القطاع الحكومي'),
    ('defense', 'الدفاع'),
    ('energy', 'الطاقة والمرافق'),
    ('manufacturing', 'التصنيع'),
    ('technology', 'التقنية'),
    ('logistics', 'النقل والخدمات اللوجستية'),
    ('construction', 'الإنشاءات'),
    ('retail', 'التجزئة'),
    ('education', 'التعليم'),
    ('other', 'أخرى'),
]
SIZE_CHOICES_AR = [
    ('micro', 'متناهية الصغر'),
    ('small', 'صغيرة'),
    ('medium', 'متوسطة'),
    ('large', 'كبيرة'),
    ('enterprise', 'مؤسسة كبرى'),
]


class CompanyRegistrationForm(forms.Form):
    """Combined form for company and user registration."""
    # Company fields
    company_name = forms.CharField(max_length=255)
    company_name_ar = forms.CharField(max_length=255, required=False)
    cr_number = forms.CharField(max_length=20)
    sector = forms.ChoiceField(choices=SECTOR_CHOICES_AR)
    size = forms.ChoiceField(choices=SIZE_CHOICES_AR)
    city = forms.CharField(max_length=100, required=False)

    # Targets
    target_nca = forms.BooleanField(required=False)
    target_aramco = forms.BooleanField(required=False)
    target_sabic = forms.BooleanField(required=False)

    # User fields
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)
    email = forms.EmailField()
    phone = forms.CharField(max_length=20, required=False)
    # FR-012.4: minimum 12 characters.
    password = forms.CharField(widget=forms.PasswordInput, min_length=12)

    def clean_cr_number(self):
        """FR-002.10: CR must be exactly 10 digits. FR-002.11: must be unique."""
        cr = (self.cleaned_data.get('cr_number') or '').strip()
        if not cr.isdigit() or len(cr) != 10:
            raise forms.ValidationError('Commercial Registration (CR) number must be exactly 10 digits.')
        if Company.objects.filter(cr_number=cr).exists():
            raise forms.ValidationError('A company with this CR number is already registered.')
        return cr

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean(self):
        cleaned = super().clean()
        if not (cleaned.get('target_nca') or cleaned.get('target_aramco') or cleaned.get('target_sabic')):
            raise forms.ValidationError('Select at least one certification target (NCA, Aramco, or SABIC).')
        return cleaned


class SelfServiceRegistrationForm(forms.Form):
    """Phase 4A — Arabic-first self-service company registration.

    Additive: does not replace CompanyRegistrationForm. Reuses the same
    validation rules (CR = 10 digits + unique, unique email, password >= 12,
    at least one compliance goal) and adds password confirmation.
    """
    # بيانات المستخدم
    first_name = forms.CharField(max_length=30, label='الاسم الأول')
    last_name = forms.CharField(max_length=30, label='اسم العائلة')
    email = forms.EmailField(label='البريد الإلكتروني')
    phone = forms.CharField(max_length=20, required=False, label='رقم الجوال')
    password = forms.CharField(
        widget=forms.PasswordInput, min_length=12, label='كلمة المرور',
        help_text='استخدم كلمة مرور قوية لا تقل عن 12 حرفًا، ويفضّل أن تحتوي على أحرف وأرقام ورمز خاص.')
    password_confirm = forms.CharField(widget=forms.PasswordInput, label='تأكيد كلمة المرور')

    # بيانات الشركة
    company_name_ar = forms.CharField(max_length=255, label='اسم الشركة بالعربية')
    company_name = forms.CharField(max_length=255, required=False, label='اسم الشركة بالإنجليزية')
    cr_number = forms.CharField(
        max_length=20, label='رقم السجل التجاري',
        help_text='رقم السجل التجاري في السعودية يتكوّن غالبًا من 10 أرقام.')
    sector = forms.ChoiceField(choices=SECTOR_CHOICES_AR, label='القطاع / نوع الجهة')
    size = forms.ChoiceField(choices=SIZE_CHOICES_AR, label='حجم الشركة')
    city = forms.CharField(max_length=100, required=False, label='المدينة')
    country = forms.CharField(max_length=100, required=False, initial='SA', label='الدولة')
    description = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False,
                                 label='وصف مختصر')

    # أهداف الامتثال
    target_nca = forms.BooleanField(required=False, label='نحتاج الامتثال لـ NCA')
    target_aramco = forms.BooleanField(required=False, label='نحتاج الامتثال لـ Aramco')
    target_sabic = forms.BooleanField(required=False, label='نحتاج الامتثال لـ SABIC')

    # Phase 8C — trust: explicit terms/privacy acceptance (form-only, not stored).
    accept_terms = forms.BooleanField(
        required=True,
        label='أوافق على شروط الاستخدام وسياسة الخصوصية الخاصة بمنصة 1SaudiCyber.',
        error_messages={'required': 'يجب الموافقة على شروط الاستخدام وسياسة الخصوصية قبل إنشاء الحساب.'})

    def clean_cr_number(self):
        cr = (self.cleaned_data.get('cr_number') or '').strip()
        if not cr.isdigit() or len(cr) != 10:
            raise forms.ValidationError('رقم السجل التجاري يجب أن يكون 10 أرقام بالضبط.')
        if Company.objects.filter(cr_number=cr).exists():
            raise forms.ValidationError('توجد شركة مسجّلة بنفس رقم السجل التجاري.')
        return cr

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('يوجد حساب مسجّل بهذا البريد الإلكتروني.')
        return email

    def clean(self):
        cleaned = super().clean()
        pw, pw2 = cleaned.get('password'), cleaned.get('password_confirm')
        if pw and pw2 and pw != pw2:
            self.add_error('password_confirm', 'كلمتا المرور غير متطابقتين.')
        if not (cleaned.get('target_nca') or cleaned.get('target_aramco') or cleaned.get('target_sabic')):
            raise forms.ValidationError('اختر هدف امتثال واحدًا على الأقل (NCA أو Aramco أو SABIC).')
        return cleaned


class LoginForm(forms.Form):
    username = forms.EmailField(label="Email")
    password = forms.CharField(widget=forms.PasswordInput)


class EvidenceUploadForm(forms.Form):
    evidence_file = forms.FileField()
    notes = forms.CharField(widget=forms.Textarea, required=False)
