"""
Django app configuration for django-4eyes.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class Django4EyesConfig(AppConfig):
    """Configuration for the django-4eyes approval workflow app."""
    
    name = 'django_4eyes'
    verbose_name = _('Approval Workflow')
    
    def ready(self):
        """Import signals when the app is ready."""
        # Import signals to connect handlers
        from django_4eyes import signals  # noqa: F401