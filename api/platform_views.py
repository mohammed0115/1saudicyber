"""Operational endpoints for platform health and capability discovery."""
from django.conf import settings
from django.db import connection
from django.http import FileResponse, Http404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    """Low-disclosure health check suitable for infrastructure probes."""
    try:
        connection.ensure_connection()
        database = 'ok'
        status_code = 200
    except Exception:
        database = 'unavailable'
        status_code = 503
    return Response({'status': 'ok' if database == 'ok' else 'degraded', 'database': database}, status=status_code)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def platform_capabilities(request):
    """Discover stable platform surfaces without exposing tenant data."""
    return Response({
        'api_version': 'v1',
        'capabilities': [
            'policy_evaluation', 'common_control_mapping', 'connector_catalog',
            'automated_control_testing', 'domain_events', 'reviewable_recommendations',
            'governed_evidence_decisions',
        ],
        'documentation': '/api/v1/platform/openapi/',
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def openapi_contract(request):
    """Serve the versioned OpenAPI contract without exposing repository browsing."""
    path = settings.BASE_DIR / 'Docs' / 'openapi' / 'platform-v1.yaml'
    if not path.exists():
        raise Http404('OpenAPI contract not found.')
    return FileResponse(path.open('rb'), content_type='application/yaml')
