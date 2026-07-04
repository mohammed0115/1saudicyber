"""CyberTrust KSA URL Configuration"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.views.generic import RedirectView


def healthz(request):
    """Lightweight liveness probe for load balancers / Docker healthcheck.

    Unauthenticated and intentionally minimal: returns only {"status": "ok"} and
    never exposes settings, versions, or other sensitive information.
    """
    return JsonResponse({'status': 'ok'})


urlpatterns = [
    path('healthz/', healthz, name='healthz'),
    path('i18n/', include('django.conf.urls.i18n')),  # set_language (bilingual switcher)
    path('admin/', admin.site.urls),
    path('api/v1/', include('api.urls')),
    path('', include('core.urls')),
    path('compliance/risks/', include('risk.urls')),
    path('compliance/', include('compliance.urls')),
    # Convenience redirect: bare /company/ -> the (login-guarded) main dashboard.
    path('company/', RedirectView.as_view(pattern_name='dashboard:main', permanent=False)),
    path('dashboard/', include('dashboard.urls')),
    path('ai/', include('ai_engine.urls')),
    path('auditor/', include('auditor_portal.urls')),
    path('auditors/', include('auditors.urls')),
    path('platform-admin/', include('auditors.admin_urls')),
    path('monitoring/', include('monitoring.urls')),
    path('billing/', include('billing.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
