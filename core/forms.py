from django import forms
from .models import User, Company
from .services import recommend_frameworks


class CompanyRegistrationForm(forms.Form):
    """Combined form for company and user registration."""
    # Company fields
    company_name = forms.CharField(max_length=255)
    company_name_ar = forms.CharField(max_length=255, required=False)
    cr_number = forms.CharField(max_length=20)
    sector = forms.ChoiceField(choices=Company.SECTOR_CHOICES)
    size = forms.ChoiceField(choices=Company.SIZE_CHOICES)
    city = forms.CharField(max_length=100, required=False)

    # Explainable onboarding questions. The framework targets are derived
    # server-side from these answers and are never trusted from the browser.
    nca_scope = forms.BooleanField(required=False)
    aramco_supplier = forms.BooleanField(required=False)
    sabic_supplier = forms.BooleanField(required=False)

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
        try:
            cleaned['framework_recommendation'] = recommend_frameworks(cleaned)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return cleaned


class LoginForm(forms.Form):
    username = forms.EmailField(label="Email")
    password = forms.CharField(widget=forms.PasswordInput)


class EvidenceUploadForm(forms.Form):
    evidence_file = forms.FileField()
    notes = forms.CharField(widget=forms.Textarea, required=False)
