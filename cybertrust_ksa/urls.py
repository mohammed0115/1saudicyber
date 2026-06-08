"""CyberTrust KSA URL Configuration"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('api.urls')),
    path('', include('core.urls')),
    path('compliance/', include('compliance.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('ai/', include('ai_engine.urls')),
    path('auditor/', include('auditor_portal.urls')),
    path('monitoring/', include('monitoring.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
