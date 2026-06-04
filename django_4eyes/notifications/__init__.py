"""
Notification plugins for django-4eyes.

This package provides a flexible notification system that supports:
- Email notifications
- Django messages framework notifications
- Custom notification backends
"""

from django_4eyes.notifications.base import NotificationPlugin, NotificationPluginRegistry
from django_4eyes.notifications.email import EmailNotificationPlugin
from django_4eyes.notifications.django_messages import DjangoMessagesNotificationPlugin
from django_4eyes.notifications.registry import registry

__all__ = [
    'NotificationPlugin',
    'NotificationPluginRegistry',
    'EmailNotificationPlugin',
    'DjangoMessagesNotificationPlugin',
    'registry',
]