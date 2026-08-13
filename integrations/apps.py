from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    """Connector catalogue, secure references, and automated control testing."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'integrations'
    verbose_name = 'Integrations and Control Testing'
