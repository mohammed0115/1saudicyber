from django.apps import AppConfig


class PlatformEventsConfig(AppConfig):
    """Reliable, schema-versioned domain events and webhook delivery records."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'platform_events'
    verbose_name = 'Platform Events'
