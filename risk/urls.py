from django.urls import path

from . import views

app_name = 'risk'

urlpatterns = [
    path('', views.risk_list, name='list'),
    path('new/', views.risk_create, name='create'),
    path('tasks/<int:task_id>/edit/', views.task_edit, name='task_edit'),
    path('assignment/<int:assignment_id>/', views.risk_auditor_view, name='auditor_view'),
    path('<int:risk_id>/', views.risk_detail, name='detail'),
    path('<int:risk_id>/edit/', views.risk_edit, name='edit'),
    path('<int:risk_id>/tasks/new/', views.task_create, name='task_create'),
]
