"""
Notification sender utility for django-4eyes.

This module provides the NotificationSender class that coordinates
sending notifications through all enabled plugins.
"""

import logging
from typing import Dict, Any, Optional, List
from django.contrib.auth.models import User, Group
from django.conf import settings

logger = logging.getLogger(__name__)


class NotificationSender:
    """
    Central notification sender that coordinates sending through all enabled plugins.
    
    Usage:
        # Send to a single user
        NotificationSender.send_to_user(
            recipient=user,
            title="Approval Required",
            message="Please review this request"
        )
        
        # Send to a group
        NotificationSender.send_to_group(
            group=approver_group,
            title="Approval Required",
            message="Please review this request"
        )
    """
    
    @staticmethod
    def send_to_user(
        recipient: User,
        title: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        plugins: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, bool]:
        """
        Send notification to a user through all enabled plugins.
        
        Args:
            recipient: User to send notification to
            title: Notification title
            message: Notification message
            context: Additional context data
            plugins: Optional list of specific plugin IDs to use (overrides settings)
            **kwargs: Additional arguments passed to plugins
            
        Returns:
            Dictionary mapping plugin_id to success status
        """
        from django_4eyes.notifications import registry
        
        results = {}
        
        # Get plugins to use
        if plugins:
            notification_plugins = [
                registry.get(plugin_id)
                for plugin_id in plugins
                if registry.get(plugin_id)
            ]
        else:
            notification_plugins = registry.get_enabled()
        
        for plugin in notification_plugins:
            if not plugin:
                continue
            
            # Check if plugin can send to this user
            if not plugin.can_send(recipient, **kwargs):
                results[plugin.plugin_id] = False
                continue
            
            try:
                success = plugin.send(
                    recipient=recipient,
                    title=title,
                    message=message,
                    context=context,
                    **kwargs
                )
                results[plugin.plugin_id] = success
            except Exception as e:
                logger.error(
                    f"Plugin {plugin.plugin_id} failed to send to {recipient.username}: {e}",
                    exc_info=True
                )
                results[plugin.plugin_id] = False
        
        return results
    
    @staticmethod
    def send_to_group(
        group: Group,
        title: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        plugins: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Dict[User, bool]]:
        """
        Send notification to all members of a group.
        
        Args:
            group: Group whose members should receive the notification
            title: Notification title
            message: Notification message
            context: Additional context data
            plugins: Optional list of specific plugin IDs to use
            **kwargs: Additional arguments passed to plugins
            
        Returns:
            Dictionary mapping plugin_id to dict of user->success status
        """
        results = {}
        
        for user in group.user_set.filter(is_active=True):
            user_results = NotificationSender.send_to_user(
                recipient=user,
                title=title,
                message=message,
                context=context,
                plugins=plugins,
                **kwargs
            )
            
            # Merge results
            for plugin_id, success in user_results.items():
                if plugin_id not in results:
                    results[plugin_id] = {}
                results[plugin_id][user] = success
        
        return results
    
    @staticmethod
    def send_to_users(
        recipients: List[User],
        title: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        plugins: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Dict[User, bool]]:
        """
        Send notification to multiple users.
        
        Args:
            recipients: List of users to send notification to
            title: Notification title
            message: Notification message
            context: Additional context data
            plugins: Optional list of specific plugin IDs to use
            **kwargs: Additional arguments passed to plugins
            
        Returns:
            Dictionary mapping plugin_id to dict of user->success status
        """
        results = {}
        
        for user in recipients:
            user_results = NotificationSender.send_to_user(
                recipient=user,
                title=title,
                message=message,
                context=context,
                plugins=plugins,
                **kwargs
            )
            
            # Merge results
            for plugin_id, success in user_results.items():
                if plugin_id not in results:
                    results[plugin_id] = {}
                results[plugin_id][user] = success
        
        return results
    
    @staticmethod
    def get_available_plugins():
        """
        Get list of available notification plugins.
        
        Returns:
            List of dicts with plugin info (plugin_id, name, description)
        """
        from django_4eyes.notifications import registry
        
        return [
            {
                'plugin_id': plugin.plugin_id,
                'name': plugin.name,
                'description': plugin.description,
                'enabled_by_default': plugin.enabled_by_default,
            }
            for plugin in registry.get_all()
        ]
    
    @staticmethod
    def get_enabled_plugins():
        """
        Get list of enabled notification plugins.
        
        Returns:
            List of dicts with plugin info
        """
        from django_4eyes.notifications import registry
        
        return [
            {
                'plugin_id': plugin.plugin_id,
                'name': plugin.name,
                'description': plugin.description,
            }
            for plugin in registry.get_enabled()
        ]