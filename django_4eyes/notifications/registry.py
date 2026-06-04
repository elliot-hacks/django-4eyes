"""
Global notification plugin registry.
"""

from django_4eyes.notifications.base import NotificationPluginRegistry

# Global registry instance
registry = NotificationPluginRegistry()


def register_default_plugins():
    """Register the default notification plugins."""
    from django_4eyes.notifications.email import EmailNotificationPlugin
    from django_4eyes.notifications.django_messages import DjangoMessagesNotificationPlugin
    
    # Register default plugins
    registry.register(EmailNotificationPlugin())
    registry.register(DjangoMessagesNotificationPlugin())


# Auto-register default plugins when this module is imported
register_default_plugins()