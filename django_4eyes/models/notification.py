"""
Notification models for django-4eyes approval workflow engine.
"""

from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    """
    Notification system for approval workflows.
    
    Notifications are created when approval actions are required,
    and track whether approvers have acted on them.
    
    Example:
        # Get pending approval notifications for a user
        notifications = Notification.objects.filter(
            recipient=user,
            notification_type='approval_required',
            acted=False
        )
    """
    
    NOTIFICATION_TYPES = (
        ('approval_required', _('Approval Required')),
        ('approval_action', _('Approval Action Taken')),
        ('approval_completed', _('Approval Completed')),
        ('changes_requested', _('Changes Requested')),
        ('system', _('System Notification')),
    )
    
    ACTION_TYPES = (
        ('approved', _('Approved')),
        ('rejected', _('Rejected')),
        ('commented', _('Commented')),
        ('changes_requested', _('Changes Requested')),
    )
    
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='approval_notifications',
        null=True,
        blank=True,
        help_text=_("User who should receive this notification")
    )
    
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        help_text=_("Type of notification")
    )
    
    title = models.CharField(
        max_length=255,
        help_text=_("Notification title")
    )
    
    message = models.TextField(
        blank=True,
        help_text=_("Notification message content")
    )
    
    is_read = models.BooleanField(
        default=False,
        help_text=_("Whether the recipient has read this notification")
    )
    
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the notification was read")
    )
    
    # Approval-specific fields
    step = models.ForeignKey(
        'ApprovalStep',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text=_("Approval step this notification is for")
    )
    
    acted = models.BooleanField(
        default=False,
        help_text=_("Whether the recipient has acted on this notification")
    )
    
    action_taken = models.CharField(
        max_length=20,
        blank=True,
        choices=ACTION_TYPES,
        help_text=_("Action taken by the recipient")
    )
    
    # Generic relation to the object being approved
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text=_("Type of the related object")
    )
    
    object_id = models.CharField(
        max_length=36,
        null=True,
        blank=True,
        help_text=_("ID of the related object")
    )
    
    content_object = GenericForeignKey('content_type', 'object_id')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='created_notifications'
    )
    
    class Meta:
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['recipient', 'acted']),
            models.Index(fields=['content_type', 'object_id']),
        ]
    
    def __str__(self):
        recipient_name = self.recipient.username if self.recipient else "System"
        return f"{self.title} - {recipient_name}"
    
    def mark_as_read(self):
        """Mark notification as read."""
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at', 'updated_at'])
    
    def mark_as_acted(self, action_taken, message=""):
        """Mark notification as acted with optional message update."""
        self.acted = True
        self.action_taken = action_taken
        if message:
            self.message = message
        self.save(update_fields=['acted', 'action_taken', 'message', 'updated_at'])
    
    def get_available_actions(self, user):
        """Get available actions for this notification."""
        if (self.notification_type == 'approval_required' and 
            not self.acted and 
            self.step and 
            self.content_object):
            return self.step.get_available_actions(user)
        return []
    
    def get_absolute_url(self):
        """Get URL to view the related object."""
        if self.content_type and self.object_id:
            try:
                model_class = self.content_type.model_class()
                if model_class:
                    # Try to get admin URL
                    return f'/admin/{self.content_type.app_label}/{self.content_type.model}/{self.object_id}/change/'
            except Exception:
                pass
        return None
    
    def get_object_summary(self):
        """Get summary of the related object."""
        if not self.content_object:
            return "Object not found"
        
        obj = self.content_object
        summary_parts = []
        
        # Common fields
        field_mapping = [
            ('number', 'Number: {}'),
            ('title', 'Title: {}'),
            ('name', 'Name: {}'),
            ('subject', 'Subject: {}'),
            ('description', 'Description: {}'),
            ('total_amount', 'Amount: ${:,.2f}'),
            ('status', 'Status: {}'),
        ]
        
        for field, template in field_mapping:
            if hasattr(obj, field):
                value = getattr(obj, field)
                if value:
                    try:
                        summary_parts.append(template.format(value))
                    except (ValueError, TypeError):
                        summary_parts.append(template.format(str(value)))
        
        return "\n".join(summary_parts) if summary_parts else str(obj)
    
    def get_object_type_display(self):
        """Get human-readable object type."""
        if self.content_type:
            try:
                return self.content_type.model_class()._meta.verbose_name.title()
            except Exception:
                return self.content_type.model
        return "Unknown Object"
    
    @property
    def content_object_unfiltered(self):
        """
        Retrieve the linked content object bypassing any approval-gating manager.
        """
        if not self.content_type_id or not self.object_id:
            return None
        
        model_class = self.content_type.model_class()
        if model_class is None:
            return None
        
        manager = getattr(model_class, 'all_objects', model_class._default_manager)
        
        try:
            return manager.get(pk=self.object_id)
        except model_class.DoesNotExist:
            return None