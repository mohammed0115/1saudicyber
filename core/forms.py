from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Company


class CompanyRegistrationForm(forms.Form):
    """Combined form for company and user registration."""
    # Company fields
    company_name = forms.CharField(max_length=255)
    company_name_ar = forms.CharField(max_length=255, required=False)
    cr_number = forms.CharField(max_length=20)
    sector = forms.ChoiceField(choices=Company.SECTOR_CHOICES)
    size = forms.ChoiceField(choices=Company.SIZE_CHOICES)
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


class LoginForm(forms.Form):
    username = forms.EmailField(label="Email")
    password = forms.CharField(widget=forms.PasswordInput)


class EvidenceUploadForm(forms.Form):
    evidence_file = forms.FileField()
    notes = forms.CharField(widget=forms.Textarea, required=False)
