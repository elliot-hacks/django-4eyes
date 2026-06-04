"""
Base notification plugin class and registry.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from django.contrib.auth.models import User


class NotificationPlugin(ABC):
    """
    Abstract base class for notification plugins.
    
    All notification plugins must inherit from this class and implement
    the send() method.
    """
    
    # Unique identifier for this plugin
    plugin_id: str = ''
    
    # Human-readable name
    name: str = ''
    
    # Description of what this plugin does
    description: str = ''
    
    # Whether this plugin is enabled by default
    enabled_by_default: bool = True
    
    @abstractmethod
    def send(
        self,
        recipient: User,
        title: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> bool:
        """
        Send a notification to a user.
        
        Args:
            recipient: The user to send the notification to
            title: Notification title
            message: Notification message body
            context: Additional context data (optional)
            **kwargs: Additional arguments
            
        Returns:
            True if notification was sent successfully, False otherwise
        """
        pass
    
    def can_send(self, recipient: User, **kwargs) -> bool:
        """
        Check if notification can be sent to this user.
        
        Override this method to add custom logic for determining
        if a notification should be sent.
        
        Args:
            recipient: The user to check
            **kwargs: Additional context
            
        Returns:
            True if notification can be sent, False otherwise
        """
        return True
    
    def get_template_context(
        self,
        title: str,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get context for template rendering.
        
        Args:
            title: Notification title
            message: Notification message
            context: Additional context
            
        Returns:
            Dictionary of template context
        """
        return {
            'title': title,
            'message': message,
            **(context or {})
        }


class NotificationPluginRegistry:
    """
    Registry for notification plugins.
    
    This class manages the registration and retrieval of notification plugins.
    """
    
    def __init__(self):
        self._plugins: Dict[str, NotificationPlugin] = {}
    
    def register(self, plugin: NotificationPlugin) -> None:
        """
        Register a notification plugin.
        
        Args:
            plugin: The plugin to register
        """
        if not plugin.plugin_id:
            raise ValueError("Plugin must have a plugin_id")
        
        self._plugins[plugin.plugin_id] = plugin
    
    def unregister(self, plugin_id: str) -> None:
        """
        Unregister a notification plugin.
        
        Args:
            plugin_id: The ID of the plugin to unregister
        """
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]
    
    def get(self, plugin_id: str) -> Optional[NotificationPlugin]:
        """
        Get a plugin by ID.
        
        Args:
            plugin_id: The plugin ID
            
        Returns:
            The plugin, or None if not found
        """
        return self._plugins.get(plugin_id)
    
    def get_all(self) -> List[NotificationPlugin]:
        """
        Get all registered plugins.
        
        Returns:
            List of all plugins
        """
        return list(self._plugins.values())
    
    def get_enabled(self) -> List[NotificationPlugin]:
        """
        Get all enabled plugins.
        
        Returns:
            List of enabled plugins
        """
        from django.conf import settings
        
        # Get enabled plugins from settings
        enabled_plugins = getattr(
            settings,
            'FOUREYES_ENABLED_NOTIFICATION_PLUGINS',
            None
        )
        
        if enabled_plugins is None:
            # Use default (all plugins enabled by default)
            return [p for p in self._plugins.values() if p.enabled_by_default]
        
        return [
            p for p in self._plugins.values()
            if p.plugin_id in enabled_plugins
        ]
    
    def is_registered(self, plugin_id: str) -> bool:
        """
        Check if a plugin is registered.
        
        Args:
            plugin_id: The plugin ID
            
        Returns:
            True if registered, False otherwise
        """
        return plugin_id in self._plugins
    
    def clear(self) -> None:
        """Clear all registered plugins."""
        self._plugins.clear()