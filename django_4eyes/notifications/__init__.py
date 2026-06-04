"""
Notification plugins for django-4eyes.

This package provides a flexible notification system that supports:
- Email notifications
- Django messages framework notifications
- Custom notification backends

Usage:
    from django_4eyes.notifications import NotificationSender
    
    # Send notification to a user
    NotificationSender.send_to_user(
        recipient=user,
        title="Approval Required",
        message="Please review this request"
    )
"""

from django_4eyes.notifications.base import NotificationPlugin, NotificationPluginRegistry
from django_4eyes.notifications.email import EmailNotificationPlugin
from django_4eyes.notifications.django_messages import DjangoMessagesNotificationPlugin
from django_4eyes.notifications.registry import registry
from django_4eyes.notifications.sender import NotificationSender

__all__ = [
    'NotificationPlugin',
    'NotificationPluginRegistry',
    'EmailNotificationPlugin',
    'DjangoMessagesNotificationPlugin',
    'registry',
    'NotificationSender',
]
