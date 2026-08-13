from rest_framework import serializers

from platform_events.models import ControlStatusRecommendation, DomainEvent, WebhookSubscription


class DomainEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = DomainEvent
        fields = ['event_id', 'event_type', 'schema_version', 'payload', 'trace_id', 'status', 'created_at', 'published_at']
        read_only_fields = fields


class WebhookSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookSubscription
        fields = ['id', 'name', 'url', 'event_types', 'signing_secret_reference', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        instance = WebhookSubscription(company=self.context['company'], **attrs)
        instance.full_clean()
        return attrs


class ControlStatusRecommendationSerializer(serializers.ModelSerializer):
    control_id = serializers.CharField(source='company_control.control.control_id', read_only=True)
    test_outcome = serializers.CharField(source='test_result.outcome', read_only=True)

    class Meta:
        model = ControlStatusRecommendation
        fields = [
            'id', 'control_id', 'test_outcome', 'proposed_status', 'rule_reference',
            'rationale', 'status', 'created_at', 'reviewed_at',
        ]
        read_only_fields = fields


class RecommendationReviewSerializer(serializers.Serializer):
    accept = serializers.BooleanField()
