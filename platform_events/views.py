"""Tenant-scoped event visibility, webhook configuration, and recommendation review APIs."""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.permissions import require_company
from platform_events.models import ControlStatusRecommendation, DomainEvent, WebhookSubscription
from platform_events.serializers import (
    ControlStatusRecommendationSerializer,
    DomainEventSerializer,
    RecommendationReviewSerializer,
    WebhookSubscriptionSerializer,
)
from platform_events.services import review_status_recommendation


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def events(request):
    company = require_company(request)
    if company is None:
        return Response({'detail': 'Superusers must select a tenant through an administration flow.'}, status=400)
    rows = DomainEvent.objects.filter(company=company).order_by('-created_at')[:100]
    return Response(DomainEventSerializer(rows, many=True).data)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def webhook_subscriptions(request):
    company = require_company(request)
    if company is None:
        return Response({'detail': 'Superusers must select a tenant through an administration flow.'}, status=400)
    if request.method == 'GET':
        return Response(WebhookSubscriptionSerializer(
            WebhookSubscription.objects.filter(company=company), many=True,
        ).data)
    serializer = WebhookSubscriptionSerializer(data=request.data, context={'company': company})
    serializer.is_valid(raise_exception=True)
    subscription = WebhookSubscription(company=company, **serializer.validated_data)
    subscription.full_clean()
    subscription.save()
    return Response(WebhookSubscriptionSerializer(subscription).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def status_recommendations(request):
    company = require_company(request)
    if company is None:
        return Response({'detail': 'Superusers must select a tenant through an administration flow.'}, status=400)
    rows = ControlStatusRecommendation.objects.filter(company_control__company=company).select_related(
        'company_control__control', 'test_result',
    )
    return Response(ControlStatusRecommendationSerializer(rows, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def review_recommendation(request, recommendation_id):
    company = require_company(request)
    if company is None:
        return Response({'detail': 'Superusers must select a tenant through an administration flow.'}, status=400)
    try:
        recommendation = ControlStatusRecommendation.objects.select_related('company_control').get(
            id=recommendation_id, company_control__company=company,
        )
    except ControlStatusRecommendation.DoesNotExist:
        return Response({'detail': 'Recommendation not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.user.role not in {'company_admin', 'compliance_officer', 'auditor', 'admin'}:
        return Response({'detail': 'A compliance reviewer role is required.'}, status=status.HTTP_403_FORBIDDEN)
    serializer = RecommendationReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        recommendation = review_status_recommendation(
            recommendation, reviewer=request.user, accept=serializer.validated_data['accept'],
        )
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(ControlStatusRecommendationSerializer(recommendation).data)
