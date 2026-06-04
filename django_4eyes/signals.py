"""
Signal handlers for django-4eyes approval workflow engine.

This module contains signal handlers that automatically:
- Start approval workflows when objects are created
- Update approval states when objects are modified
- Clean up approval data when objects are deleted
"""

import logging
import threading
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

logger = logging.getLogger(__name__)

# Thread-local storage for preventing recursive signals
_thread_local = threading.local()


def get_current_user():
    """Get current user from thread local storage."""
    if hasattr(_thread_local, 'current_user'):
        return _thread_local.current_user
    return None


def set_current_user(user):
    """Set current user in thread local storage."""
    _thread_local.current_user = user


class SignalContext:
    """Context manager to prevent recursive signal firing."""
    
    def __init__(self, flag_name):
        self.flag_name = flag_name
    
    def __enter__(self):
        if not hasattr(_thread_local, 'signal_flags'):
            _thread_local.signal_flags = set()
        
        if self.flag_name in _thread_local.signal_flags:
            return False
        
        _thread_local.signal_flags.add(self.flag_name)
        return True
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(_thread_local, 'signal_flags'):
            _thread_local.signal_flags.discard(self.flag_name)


@receiver(post_save)
def handle_new_approvable_object(sender, instance, created, **kwargs):
    """
    Automatically start approval workflow when a FourEyeModel object is created.
    
    This signal checks if the created object:
    1. Is an instance of ApprovalMixin (has approval fields)
    2. Is not an internal approval model (ApprovalTemplate, ApprovalStep, etc.)
    3. Has an active ApprovalTemplate for its content type
    
    If all conditions are met, an ApprovalState is created and the workflow starts.
    """
    # Skip if not created
    if not created:
        return
    
    # Skip if raw import
    if kwargs.get('raw', False):
        return
    
    # Skip if _skip_signals flag is set
    if getattr(instance, '_skip_signals', False):
        return
    
    # Import here to avoid circular imports
    from django_4eyes.models import ApprovalMixin, ApprovalTemplate, ApprovalState, ApprovalStep
    
    # Only process ApprovalMixin instances
    if not isinstance(instance, ApprovalMixin):
        return
    
    # Skip internal approval models
    if isinstance(instance, (ApprovalTemplate, ApprovalStep, ApprovalState)):
        return
    
    # Use context to prevent recursive signal firing
    context_key = f'start_approval_{sender.__name__}_{instance.pk}'
    with SignalContext(context_key) as should_process:
        if not should_process:
            return
        
        try:
            _start_approval_workflow(instance)
        except Exception as e:
            logger.error(f"Error starting approval workflow for {instance}: {e}", exc_info=True)


def _start_approval_workflow(instance):
    """
    Start approval workflow for a new object.
    
    This function:
    1. Gets the ContentType for the object
    2. Finds an active ApprovalTemplate for that content type
    3. Creates an ApprovalState
    4. Sets the first step
    5. Sends notifications to approvers
    
    If no template is found, the object is auto-approved.
    """
    from django_4eyes.models import ApprovalTemplate, ApprovalState, ApprovalStep
    from django_4eyes.engine import ApprovalWorkflowEngine
    
    # Get content type
    content_type = ContentType.objects.get_for_model(instance.__class__)
    
    with transaction.atomic():
        # Check if approval state already exists
        existing = ApprovalState.objects.filter(
            content_type=content_type,
            object_id=instance.pk
        ).exists()
        
        if existing:
            return
        
        # Find active template for this content type
        template = ApprovalTemplate.objects.optimized().filter(
            content_type=content_type,
            is_active=True
        ).first()
        
        # No template - auto-approve
        if not template:
            instance.__class__.objects.filter(pk=instance.pk).update(is_approved=True)
            logger.debug(
                f"Auto-approving {instance.__class__.__name__} {instance.pk} - no template found"
            )
            return
        
        # Check if template has auto_start_approval enabled
        if not template.auto_start_approval:
            # Mark as approved but don't start workflow
            instance.is_approved = True
            instance.save(update_fields=['is_approved'])
            return
        
        # Create approval state
        approval_state = ApprovalState.objects.create(
            content_type=content_type,
            object_id=instance.pk,
            template=template,
            current_step=None,
            is_approved=False,
            is_rejected=False,
            actions_history=[],
            created_by=get_current_user()
        )
        
        # Get first step
        first_step = (
            template.prefetched_steps[0]
            if hasattr(template, 'prefetched_steps') and template.prefetched_steps
            else template.steps.filter(is_active=True).order_by('order').first()
        )
        
        if not first_step:
            return
        
        # Set current step
        approval_state.current_step = first_step
        approval_state.save(update_fields=['current_step'])
        
        # Handle auto-approve first step
        if first_step.auto_approve:
            ApprovalWorkflowEngine._auto_approve_step(approval_state, first_step)
        else:
            # Send notifications
            ApprovalWorkflowEngine._send_step_notifications(approval_state, first_step)
        
        logger.info(
            f"Started approval workflow for {instance.__class__.__name__} {instance.pk} "
            f"with template {template.name}"
        )


@receiver(post_save)
def sync_approval_state_to_object(sender, instance, created, **kwargs):
    """
    Sync approval state changes back to the target object.
    
    When an ApprovalState is approved or rejected, update the target object's
    is_approved and is_rejected fields to match.
    """
    from django_4eyes.models import ApprovalState
    
    # Only process ApprovalState instances
    if sender != ApprovalState:
        return
    
    # Skip if created (no need to sync on creation)
    if created:
        return
    
    # Check if approval status changed
    update_fields = kwargs.get('update_fields')
    if update_fields and not any(f in update_fields for f in ['is_approved', 'is_rejected']):
        return
    
    # Use context to prevent recursive signals
    context_key = f'sync_approval_{instance.pk}'
    with SignalContext(context_key) as should_process:
        if not should_process:
            return
        
        try:
            _sync_approval_to_object(instance)
        except Exception as e:
            logger.error(f"Error syncing approval state {instance.pk}: {e}", exc_info=True)


def _sync_approval_to_object(approval_state):
    """Sync approval state to the target object."""
    target = approval_state.content_object_unfiltered
    if not target:
        return
    
    # Check if sync is needed
    needs_update = False
    update_fields = []
    
    if hasattr(target, 'is_approved') and target.is_approved != approval_state.is_approved:
        target.is_approved = approval_state.is_approved
        needs_update = True
        update_fields.append('is_approved')
    
    if hasattr(target, 'is_rejected') and target.is_rejected != approval_state.is_rejected:
        target.is_rejected = approval_state.is_rejected
        needs_update = True
        update_fields.append('is_rejected')
    
    if needs_update:
        try:
            target._skip_signals = True
            target.save(update_fields=update_fields)
        finally:
            target._skip_signals = False


@receiver(post_delete)
def cleanup_approval_on_delete(sender, instance, **kwargs):
    """
    Clean up approval data when an object is deleted.
    
    This signal deletes:
    - ApprovalState records for the deleted object
    - Notification records for the deleted object
    """
    from django_4eyes.models import ApprovalMixin, ApprovalTemplate, ApprovalStep, ApprovalState, Notification
    
    # Only process ApprovalMixin instances
    if not isinstance(instance, ApprovalMixin):
        return
    
    # Skip internal approval models
    if isinstance(instance, (ApprovalTemplate, ApprovalStep, ApprovalState, Notification)):
        return
    
    # Use context to prevent recursive signals
    context_key = f'cleanup_approval_{sender.__name__}_{instance.pk}'
    with SignalContext(context_key) as should_process:
        if not should_process:
            return
        
        try:
            _cleanup_approval_data(instance)
        except Exception as e:
            logger.error(f"Error cleaning up approval data for {instance}: {e}", exc_info=True)


def _cleanup_approval_data(instance):
    """Delete approval data for a deleted object."""
    from django_4eyes.models import ApprovalState, Notification
    
    try:
        content_type = ContentType.objects.get_for_model(instance.__class__)
        
        # Delete approval states
        ApprovalState.objects.filter(
            content_type=content_type,
            object_id=instance.pk
        ).delete()
        
        # Delete notifications
        Notification.objects.filter(
            content_type=content_type,
            object_id=str(instance.pk)
        ).delete()
        
        logger.info(f"Cleaned up approval data for deleted {instance.__class__.__name__} {instance.pk}")
    
    except Exception as e:
        logger.warning(f"Failed to cleanup approval data for {instance}: {e}")


# Connect signals when this module is imported
logger.info("django-4eyes signals initialized")