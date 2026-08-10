"""Phase 5A — Arabic-first risk / remediation forms."""
from django import forms

from .models import RiskItem, RemediationTask


class RiskForm(forms.ModelForm):
    class Meta:
        model = RiskItem
        fields = ['title', 'description', 'category', 'likelihood', 'impact',
                  'residual_likelihood', 'residual_impact', 'status', 'owner_name', 'due_date']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'title': 'عنوان الخطر', 'description': 'الوصف', 'category': 'التصنيف',
            'likelihood': 'الاحتمالية (1-5)', 'impact': 'الأثر (1-5)',
            'residual_likelihood': 'الاحتمالية المتبقية', 'residual_impact': 'الأثر المتبقي',
            'status': 'الحالة', 'owner_name': 'المالك', 'due_date': 'تاريخ الاستحقاق',
        }


class RemediationTaskForm(forms.ModelForm):
    class Meta:
        model = RemediationTask
        fields = ['title', 'description', 'owner_name', 'due_date', 'priority',
                  'status', 'verification_notes']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'verification_notes': forms.Textarea(attrs={'rows': 2}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'title': 'عنوان المهمة', 'description': 'الوصف', 'owner_name': 'المالك',
            'due_date': 'تاريخ الاستحقاق', 'priority': 'الأولوية', 'status': 'الحالة',
            'verification_notes': 'ملاحظات التحقق',
        }
