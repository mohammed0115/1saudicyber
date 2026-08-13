from rest_framework import serializers

from policy_engine.models import CanonicalControl, ControlCoverageMapping, PolicyPack, PolicyVersion


class PolicyVersionSerializer(serializers.ModelSerializer):
    policy_pack = serializers.CharField(source='policy_pack.key', read_only=True)

    class Meta:
        model = PolicyVersion
        fields = [
            'id', 'policy_pack', 'version', 'status', 'effective_from', 'effective_to',
            'source_reference', 'content_hash', 'rules', 'approved_at',
        ]
        read_only_fields = fields


class PolicyPackSerializer(serializers.ModelSerializer):
    versions = PolicyVersionSerializer(many=True, read_only=True)

    class Meta:
        model = PolicyPack
        fields = ['key', 'name', 'description', 'status', 'versions']
        read_only_fields = fields


class PolicyEvaluationRequestSerializer(serializers.Serializer):
    policy_version_id = serializers.IntegerField()


class ControlCoverageMappingSerializer(serializers.ModelSerializer):
    framework = serializers.CharField(source='control.framework.code', read_only=True)
    control_id = serializers.CharField(source='control.control_id', read_only=True)
    control_title = serializers.CharField(source='control.title', read_only=True)
    policy_version = serializers.CharField(source='policy_version.version', read_only=True)

    class Meta:
        model = ControlCoverageMapping
        fields = [
            'framework', 'control_id', 'control_title', 'policy_version',
            'relationship', 'coverage_score', 'rationale',
        ]
        read_only_fields = fields


class CanonicalControlSerializer(serializers.ModelSerializer):
    mappings = ControlCoverageMappingSerializer(many=True, read_only=True)

    class Meta:
        model = CanonicalControl
        fields = ['key', 'name', 'description', 'mappings']
        read_only_fields = fields
