from django.core.management.base import BaseCommand

from integrations.models import IntegrationProvider


class Command(BaseCommand):
    help = 'Seed the safe local mock connector provider for platform development and tests.'

    def handle(self, *args, **options):
        provider, created = IntegrationProvider.objects.update_or_create(
            key='mock',
            defaults={
                'name': 'Mock/Test Connector',
                'description': (
                    'Deterministic local connector for validating platform lifecycle, '
                    'control-test, event, and webhook contracts. It does not contact external systems.'
                ),
                'auth_type': 'mock',
                'config_schema': {
                    'type': 'object',
                    'properties': {'simulate_healthy': {'type': 'boolean', 'default': True}},
                    'additionalProperties': False,
                },
                'is_active': True,
            },
        )
        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{action} provider: {provider.key}'))
