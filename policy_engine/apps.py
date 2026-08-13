from django.apps import AppConfig


class PolicyEngineConfig(AppConfig):
    """Reusable, versioned policy and common-controls capability."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'policy_engine'
    verbose_name = 'Policy Engine'
