"""Public, tenant-scoped policy and common-control platform endpoints."""
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.permissions import require_company
from policy_engine.models import CanonicalControl, ControlCoverageMapping, PolicyPack, PolicyVersion
from policy_engine.serializers import (
    CanonicalControlSerializer,
    PolicyEvaluationRequestSerializer,
    PolicyPackSerializer,
    PolicyVersionSerializer,
)
from policy_engine.services import evaluate_company_policy


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def policy_packs(request):
    """List published policy packs and their effective versions."""
    effective_versions = PolicyVersion.objects.filter(
        status='approved', effective_from__lte=timezone.localdate(),
    ).filter(effective_to__isnull=True) | PolicyVersion.objects.filter(
        status='approved', effective_from__lte=timezone.localdate(), effective_to__gte=timezone.localdate(),
    )
    packs = PolicyPack.objects.filter(status='active').prefetch_related(
        Prefetch('versions', queryset=effective_versions.order_by('-effective_from')),
    )
    return Response(PolicyPackSerializer(packs, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def evaluate_current_company(request):
    """Evaluate an approved policy version against the authenticated company."""
    company = require_company(request)
    if company is None:
        return Response({'detail': 'Superusers must select a tenant through an administration flow.'}, status=400)
    serializer = PolicyEvaluationRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        version = PolicyVersion.objects.select_related('policy_pack').get(
            id=serializer.validated_data['policy_version_id'],
        )
    except PolicyVersion.DoesNotExist:
        return Response({'detail': 'Policy version not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        result = evaluate_company_policy(version, company, user=request.user)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(result, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def policy_version_detail(request, policy_version_id):
    """Return a read-only policy contract; rules may be cached by external clients."""
    try:
        version = PolicyVersion.objects.select_related('policy_pack').get(id=policy_version_id)
    except PolicyVersion.DoesNotExist:
        return Response({'detail': 'Policy version not found.'}, status=status.HTTP_404_NOT_FOUND)
    if not version.is_effective_on() and not request.user.is_superuser:
        return Response({'detail': 'Policy version is not published.'}, status=status.HTTP_404_NOT_FOUND)
    return Response(PolicyVersionSerializer(version).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def canonical_control_detail(request, key):
    """Expose approved coverage mappings for one framework-neutral control objective."""
    try:
        canonical = CanonicalControl.objects.prefetch_related(
            Prefetch(
                'mappings',
                queryset=ControlCoverageMapping.objects.select_related(
                    'control__framework', 'policy_version',
                ).filter(policy_version__status='approved'),
            ),
        ).get(key=key)
    except CanonicalControl.DoesNotExist:
        return Response({'detail': 'Canonical control not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response(CanonicalControlSerializer(canonical).data)
