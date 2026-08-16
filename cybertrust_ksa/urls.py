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


def readyz(request):
    """Readiness probe — verifies the DB (and cache) are reachable. 503 if not.

    For orchestrators (k8s readiness): a running web process with a dead DB should
    be pulled from the LB. Still minimal — no settings/version leakage.
    """
    checks = {'db': 'ok', 'cache': 'ok'}
    healthy = True
    try:
        from django.db import connection
        with connection.cursor() as c:
            c.execute('SELECT 1')
            c.fetchone()
    except Exception:
        checks['db'] = 'down'; healthy = False
    try:
        from django.core.cache import cache
        cache.set('readyz', '1', 5)
        cache.get('readyz')
    except Exception:
        checks['cache'] = 'degraded'  # cache is non-fatal for readiness
    status = 'ok' if healthy else 'error'
    return JsonResponse({'status': status, **checks}, status=200 if healthy else 503)


urlpatterns = [
    path('healthz/', healthz, name='healthz'),
    path('readyz/', readyz, name='readyz'),
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

handler404 = 'core.views.public_404'
