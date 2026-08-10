"""Phase 4C — Arabic-first auditor registration form.
Phase 8D-3D-CRM-B — Get Solution CRM link/unlink forms (reason required)."""
from django import forms

from core.models import User


class LinkUserToCompanyForm(forms.Form):
    """Link an existing (unlinked) user account to a company. Reason required."""
    user_id = forms.IntegerField(min_value=1)
    reason = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={'rows': 2}),
                             label='السبب')


class UnlinkUserFromCompanyForm(forms.Form):
    """Unlink a user from its company. Reason required."""
    user_id = forms.IntegerField(min_value=1)
    reason = forms.CharField(max_length=1000, label='السبب')


class CompanyCRMNoteForm(forms.Form):
    """Internal CRM note (staff only). Text required."""
    text = forms.CharField(max_length=5000, widget=forms.Textarea(attrs={'rows': 3}),
                           label='ملاحظة داخلية')


class CompanyCRMStatusForm(forms.Form):
    """Update a company's internal CRM follow-up status (staff only)."""
    from .models import CompanyCRMProfile
    crm_status = forms.ChoiceField(choices=CompanyCRMProfile.CRM_STATUS_CHOICES, label='حالة المتابعة')
    assigned_staff_id = forms.IntegerField(required=False, min_value=0)
    next_follow_up_date = forms.DateField(required=False, label='تاريخ المتابعة التالي')
    internal_summary = forms.CharField(max_length=5000, required=False,
                                       widget=forms.Textarea(attrs={'rows': 2}), label='ملخص داخلي')
    reason = forms.CharField(max_length=1000, required=False, label='السبب')


class AuditorRegistrationForm(forms.Form):
    full_name = forms.CharField(max_length=160, label='الاسم الكامل')
    email = forms.EmailField(label='البريد الإلكتروني')
    password = forms.CharField(widget=forms.PasswordInput, min_length=12, label='كلمة المرور')
    password_confirm = forms.CharField(widget=forms.PasswordInput, label='تأكيد كلمة المرور')
    organization_name = forms.CharField(max_length=200, required=False, label='اسم الجهة (اختياري)')
    license_or_membership_no = forms.CharField(max_length=120, required=False, label='رقم الترخيص/العضوية (اختياري)')
    city = forms.CharField(max_length=100, required=False, label='المدينة')
    specialization = forms.CharField(max_length=160, required=False, label='التخصص')
    bio = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False, label='نبذة مختصرة (اختياري)')

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
        return cleaned
