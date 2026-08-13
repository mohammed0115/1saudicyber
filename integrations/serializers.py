from rest_framework import serializers

from integrations.models import (
    ControlTestDefinition,
    ControlTestResult,
    ControlTestRun,
    IntegrationConnection,
    IntegrationProvider,
)


class IntegrationProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationProvider
        fields = ['key', 'name', 'description', 'auth_type', 'config_schema']
        read_only_fields = fields


class IntegrationConnectionSerializer(serializers.ModelSerializer):
    provider = serializers.CharField(source='provider.key', read_only=True)

    class Meta:
        model = IntegrationConnection
        fields = [
            'id', 'provider', 'name', 'status', 'credential_reference', 'configuration',
            'last_checked_at', 'last_error', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'provider', 'status', 'last_checked_at', 'last_error', 'created_at', 'updated_at']


class IntegrationConnectionCreateSerializer(serializers.Serializer):
    provider_key = serializers.SlugField(max_length=80)
    name = serializers.CharField(max_length=255)
    credential_reference = serializers.CharField(max_length=255, required=False, allow_blank=True)
    configuration = serializers.JSONField(required=False, default=dict)

    def validate_provider_key(self, value):
        try:
            provider = IntegrationProvider.objects.get(key=value, is_active=True)
        except IntegrationProvider.DoesNotExist:
            raise serializers.ValidationError('Active provider not found.')
        self.context['provider'] = provider
        return value

    def validate_configuration(self, value):
        blocked = {'secret', 'token', 'password', 'api_key', 'private_key'}
        if blocked.intersection({str(key).lower() for key in value.keys()}):
            raise serializers.ValidationError('Secrets must be held by an external vault, not request configuration.')
        return value


class ControlTestDefinitionSerializer(serializers.ModelSerializer):
    connection = serializers.IntegerField(source='connection_id', read_only=True)
    control_ids = serializers.SerializerMethodField()

    class Meta:
        model = ControlTestDefinition
        fields = [
            'id', 'key', 'name', 'description', 'connection', 'control_ids',
            'schedule_minutes', 'parameters', 'enabled', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_control_ids(self, instance):
        return list(instance.controls.values_list('control_id', flat=True))


class ControlTestDefinitionCreateSerializer(serializers.Serializer):
    key = serializers.SlugField(max_length=100)
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    connection_id = serializers.IntegerField()
    control_ids = serializers.ListField(child=serializers.CharField(max_length=50), min_length=1)
    schedule_minutes = serializers.IntegerField(min_value=15, max_value=1440, required=False, default=1440)
    parameters = serializers.JSONField(required=False, default=dict)


class ControlTestResultSerializer(serializers.ModelSerializer):
    control_id = serializers.CharField(source='control.control_id', read_only=True)

    class Meta:
        model = ControlTestResult
        fields = ['control_id', 'outcome', 'summary', 'evidence_uri', 'evidence_hash', 'observed_at']
        read_only_fields = fields


class ControlTestRunSerializer(serializers.ModelSerializer):
    results = ControlTestResultSerializer(many=True, read_only=True)
    definition_key = serializers.CharField(source='definition.key', read_only=True)

    class Meta:
        model = ControlTestRun
        fields = [
            'id', 'definition_key', 'status', 'trigger', 'trace_id', 'idempotency_key',
            'started_at', 'completed_at', 'error_message', 'results',
        ]
        read_only_fields = fields
