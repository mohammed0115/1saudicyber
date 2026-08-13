"""Tenant-scoped integration and automated-control-testing API endpoints."""
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.permissions import require_company, tenant_control_queryset
from integrations.models import ControlTestDefinition, ControlTestRun, IntegrationConnection, IntegrationProvider
from integrations.serializers import (
    ControlTestDefinitionCreateSerializer,
    ControlTestDefinitionSerializer,
    ControlTestRunSerializer,
    IntegrationConnectionCreateSerializer,
    IntegrationConnectionSerializer,
    IntegrationProviderSerializer,
)
from integrations.services import execute_control_test, test_connection


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def provider_catalog(request):
    return Response(IntegrationProviderSerializer(
        IntegrationProvider.objects.filter(is_active=True), many=True,
    ).data)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def connections(request):
    company = require_company(request)
    if company is None:
        return Response({'detail': 'Superusers must select a tenant through an administration flow.'}, status=400)
    if request.method == 'GET':
        rows = IntegrationConnection.objects.filter(company=company).select_related('provider')
        return Response(IntegrationConnectionSerializer(rows, many=True).data)

    serializer = IntegrationConnectionCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    connection = IntegrationConnection(
        company=company,
        provider=serializer.context['provider'],
        name=serializer.validated_data['name'],
        credential_reference=serializer.validated_data.get('credential_reference', ''),
        configuration=serializer.validated_data.get('configuration', {}),
        created_by=request.user,
    )
    connection.full_clean()
    connection.save()
    return Response(IntegrationConnectionSerializer(connection).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def connection_test(request, connection_id):
    company = require_company(request)
    if company is None:
        return Response({'detail': 'Superusers must select a tenant through an administration flow.'}, status=400)
    try:
        connection = IntegrationConnection.objects.select_related('provider').get(id=connection_id, company=company)
    except IntegrationConnection.DoesNotExist:
        return Response({'detail': 'Connection not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response(test_connection(connection))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def control_test_definitions(request):
    company = require_company(request)
    if company is None:
        return Response({'detail': 'Superusers must select a tenant through an administration flow.'}, status=400)
    if request.method == 'GET':
        rows = ControlTestDefinition.objects.filter(company=company).prefetch_related('controls')
        return Response(ControlTestDefinitionSerializer(rows, many=True).data)

    serializer = ControlTestDefinitionCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        connection = IntegrationConnection.objects.get(
            id=serializer.validated_data['connection_id'], company=company,
        )
    except IntegrationConnection.DoesNotExist:
        return Response({'detail': 'Connection not found.'}, status=status.HTTP_404_NOT_FOUND)
    available = {
        control.control_id: control
        for control in tenant_control_queryset(company).filter(
            control__control_id__in=serializer.validated_data['control_ids'],
        ).select_related('control')
    }
    requested = set(serializer.validated_data['control_ids'])
    if requested != set(available):
        return Response({'detail': 'Every test control must be applicable to the current tenant.'}, status=400)

    with transaction.atomic():
        definition = ControlTestDefinition.objects.create(
            company=company,
            connection=connection,
            key=serializer.validated_data['key'],
            name=serializer.validated_data['name'],
            description=serializer.validated_data.get('description', ''),
            schedule_minutes=serializer.validated_data['schedule_minutes'],
            parameters=serializer.validated_data['parameters'],
            created_by=request.user,
        )
        definition.controls.set([row.control for row in available.values()])
    return Response(ControlTestDefinitionSerializer(definition).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def run_control_test(request, definition_id):
    company = require_company(request)
    if company is None:
        return Response({'detail': 'Superusers must select a tenant through an administration flow.'}, status=400)
    try:
        definition = ControlTestDefinition.objects.select_related('connection__provider').get(
            id=definition_id, company=company,
        )
    except ControlTestDefinition.DoesNotExist:
        return Response({'detail': 'Control test definition not found.'}, status=status.HTTP_404_NOT_FOUND)
    idempotency_key = request.headers.get('Idempotency-Key')
    try:
        run = execute_control_test(definition, trigger='manual', idempotency_key=idempotency_key)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(ControlTestRunSerializer(run).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def control_test_run_detail(request, run_id):
    company = require_company(request)
    if company is None:
        return Response({'detail': 'Superusers must select a tenant through an administration flow.'}, status=400)
    try:
        run = ControlTestRun.objects.select_related('definition').prefetch_related('results__control').get(
            id=run_id, company=company,
        )
    except ControlTestRun.DoesNotExist:
        return Response({'detail': 'Control test run not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response(ControlTestRunSerializer(run).data)
