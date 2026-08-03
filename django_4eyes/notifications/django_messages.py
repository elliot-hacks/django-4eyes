"""
Django Messages notification plugin for django-4eyes.
"""

import logging
from typing import Dict, Any, List, Optional
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.cache import cache

from django_4eyes.notifications.base import NotificationPlugin

logger = logging.getLogger(__name__)

# django.contrib.messages storage backends (session/cookie) require a live
# request to attach to, but notifications are sent outside the request/response
# cycle (e.g. from signal handlers, background jobs). We stash pending
# messages in the cache instead, keyed per user, and let callers drain them
# via get_messages_for_user() whenever a request is available.
CACHE_KEY_PREFIX = 'django_4eyes:messages:'
CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 7 days


class DjangoMessagesNotificationPlugin(NotificationPlugin):
    """
    Django Messages notification plugin.
    
    Sends approval notifications using Django's messages framework.
    These notifications appear as flash messages in the Django admin or
    any page that uses the messages framework.
    """
    
    plugin_id = 'django_messages'
    name = 'Django Messages'
    description = 'Send approval notifications via Django messages framework'
    enabled_by_default = True
    
    # Message level constants
    LEVELS = {
        'debug': messages.DEBUG,
        'info': messages.INFO,
        'success': messages.SUCCESS,
        'warning': messages.WARNING,
        'error': messages.ERROR,
    }
    
    def send(
        self,
        recipient: User,
        title: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> bool:
        """
        Send a Django message notification.
        
        Note: This plugin stores messages in the message storage backend.
        The messages will be displayed to the user on their next page load.
        
        Args:
            recipient: User to send message to
            title: Message title
            message: Message body
            context: Additional context
            **kwargs: Additional arguments (can include 'level' for message level)
            
        Returns:
            True if message was stored successfully
        """
        try:
            # Get message level from kwargs or context
            level = kwargs.get('level', 'info')
            message_level = self.LEVELS.get(level.lower(), messages.INFO)

            # Format the message
            formatted_message = self._format_message(title, message, context)

            # Queue the message in the cache for this user, to be drained
            # the next time a request-bound consumer calls get_messages_for_user()
            cache_key = self._cache_key(recipient)
            stored_messages = cache.get(cache_key, [])
            stored_messages.append({
                'level': message_level,
                'message': formatted_message,
            })
            cache.set(cache_key, stored_messages, CACHE_TIMEOUT)

            logger.info(f"Django message stored for user {recipient.username}: {title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store Django message for {recipient.username}: {e}", exc_info=True)
            return False
    
    def _format_message(
        self,
        title: str,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Format the message for display.
        
        Args:
            title: Message title
            message: Message body
            context: Additional context
            
        Returns:
            Formatted message string
        """
        # Combine title and message
        if title and message:
            return f"{title}\n{message}"
        elif title:
            return title
        else:
            return message or ''
    
    def can_send(self, recipient: User, **kwargs) -> bool:
        """
        Check if Django message can be sent to this user.
        
        Args:
            recipient: User to check
            **kwargs: Additional context
            
        Returns:
            True if message can be sent
        """
        # Check if user is active
        if not recipient.is_active:
            return False
        
        # Check if messages are enabled for this user
        if hasattr(recipient, 'django_messages_enabled'):
            if not recipient.django_messages_enabled:
                return False
        
        return True
    
    @staticmethod
    def _cache_key(user: User) -> str:
        return f'{CACHE_KEY_PREFIX}{user.pk}'

    @staticmethod
    def get_messages_for_user(user: User, clear: bool = True) -> List[Dict[str, Any]]:
        """
        Get stored messages for a user.

        This is useful for retrieving messages that were stored
        but not yet displayed, e.g. from a view or context processor
        that then forwards them into django.contrib.messages for the
        current request.

        Args:
            user: The user to get messages for
            clear: Whether to remove the messages from storage after reading

        Returns:
            List of dicts with 'level' and 'message' keys
        """
        cache_key = DjangoMessagesNotificationPlugin._cache_key(user)
        stored_messages = cache.get(cache_key, [])
        if clear and stored_messages:
            cache.delete(cache_key)
        return stored_messages