from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.main_dashboard, name='main'),
    path('executive/', views.executive_dashboard, name='executive'),
    path('compliance/', views.compliance_officer_dashboard, name='compliance_officer'),
    path('it-security/', views.it_security_dashboard, name='it_security'),
    path('business-unit/', views.bu_manager_dashboard, name='bu_manager'),
    path('reports/gap-analysis.pdf', views.gap_report_pdf, name='gap_report_pdf'),
    path('reports/controls.xlsx', views.compliance_export_xlsx, name='compliance_export_xlsx'),
]
