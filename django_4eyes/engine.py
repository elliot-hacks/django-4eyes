"""
Approval workflow engine for django-4eyes.

This module contains the ApprovalWorkflowEngine class that handles
all approval workflow operations.
"""

import logging
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


class ApprovalWorkflowEngine:
    """
    Main engine for handling approval workflows.
    
    This class provides methods for:
    - Advancing approval to the next step
    - Rejecting approval requests
    - Requesting changes
    - Restarting approval processes
    
    Example:
        from django_4eyes.engine import ApprovalWorkflowEngine
        
        # Approve
        approval_state = ApprovalWorkflowEngine.advance_approval(
            approval_state=state,
            actor_user=request.user,
            comment="Looks good"
        )
        
        # Reject
        approval_state = ApprovalWorkflowEngine.reject_approval(
            approval_state=state,
            actor_user=request.user,
            comment="Needs revision"
        )
    """
    
    @staticmethod
    @transaction.atomic
    def advance_approval(approval_state, actor_user, comment=None):
        """
        Advance approval to the next step or complete if all steps are done.
        
        Args:
            approval_state: The ApprovalState instance to advance
            actor_user: The user performing the approval
            comment: Optional comment from the approver
        
        Returns:
            The updated ApprovalState instance
        
        Raises:
            PermissionDenied: If user cannot approve this step
        """
        # Lock and refresh the approval state
        approval_state = ApprovalState.objects.select_for_update().select_related(
            'current_step', 'template', 'content_type'
        ).get(pk=approval_state.pk)
        
        current_step = approval_state.current_step
        if not current_step:
            raise ValidationError(_("No current step to approve"))
        
        if not current_step.can_user_approve(actor_user):
            raise PermissionDenied(
                _("User %(user)s cannot approve this step") % {'user': actor_user}
            )
        
        # Record the approval action
        if not approval_state.actions_history:
            approval_state.actions_history = []
        
        approval_state.actions_history.append({
            'action': 'approved',
            'step_id': str(current_step.id),
            'step_order': current_step.order,
            'user_id': str(actor_user.id),
            'username': actor_user.username,
            'comment': comment or '',
            'timestamp': timezone.now().isoformat()
        })
        
        # Delete notifications for this step
        from django_4eyes.models import Notification
        Notification.objects.filter(
            content_type=approval_state.content_type,
            object_id=str(approval_state.object_id),
            step=current_step,
            notification_type='approval_required'
        ).delete()
        
        # Find next step
        next_step = approval_state.template.steps.filter(
            order__gt=current_step.order
        ).first()
        
        if next_step:
            # Move to next step
            approval_state.current_step = next_step
            approval_state.save(update_fields=['current_step', 'actions_history'])
            
            # Handle auto-approve steps
            if next_step.auto_approve:
                ApprovalWorkflowEngine._auto_approve_step(approval_state, next_step)
            else:
                # Send notifications for next step
                ApprovalWorkflowEngine._send_step_notifications(approval_state, next_step)
        else:
            # All steps completed - approve the object
            approval_state.is_approved = True
            approval_state.current_step = None
            approval_state.save(update_fields=['is_approved', 'current_step', 'actions_history'])
            
            # Delete any remaining notifications
            Notification.objects.filter(
                content_type=approval_state.content_type,
                object_id=str(approval_state.object_id),
                notification_type='approval_required'
            ).delete()
            
            # Update the target object
            target = approval_state.content_object_unfiltered
            if target:
                target.is_approved = True
                target.save(update_fields=['is_approved'])
            
            # Send completion notification
            ApprovalWorkflowEngine._send_completion_notification(approval_state)
        
        logger.info(
            f"Approval advanced for {approval_state.object_id} by {actor_user} "
            f"at step {current_step.order}"
        )
        
        return approval_state
    
    @staticmethod
    @transaction.atomic
    def reject_approval(approval_state, actor_user, comment=None):
        """
        Reject the approval request, cancelling the entire process.
        
        Args:
            approval_state: The ApprovalState instance to reject
            actor_user: The user performing the rejection
            comment: Optional comment explaining the rejection
        
        Returns:
            The updated ApprovalState instance
        """
        approval_state = ApprovalState.objects.select_for_update().get(pk=approval_state.pk)
        
        if not approval_state.actions_history:
            approval_state.actions_history = []
        
        current_step = approval_state.current_step
        
        # Update state
        approval_state.is_rejected = True
        approval_state.is_approved = False
        approval_state.current_step = None
        
        approval_state.actions_history.append({
            'action': 'rejected',
            'user_id': str(actor_user.id),
            'username': actor_user.username,
            'comment': comment or '',
            'timestamp': timezone.now().isoformat(),
            'step_id': str(current_step.id) if current_step else None,
            'step_order': current_step.order if current_step else None,
        })
        
        approval_state.save(
            update_fields=['is_rejected', 'is_approved', 'current_step', 'actions_history']
        )
        
        # Delete all approval notifications
        from django_4eyes.models import Notification
        Notification.objects.filter(
            content_type=approval_state.content_type,
            object_id=str(approval_state.object_id),
            notification_type__in=['approval_required', 'approval_action']
        ).delete()
        
        # Update the target object
        target_object = approval_state.content_object_unfiltered
        if target_object:
            try:
                target_object._skip_signals = True
                if hasattr(target_object, 'is_rejected'):
                    target_object.is_rejected = True
                    target_object.is_approved = False
                    target_object.save(update_fields=['is_rejected', 'is_approved'])
            finally:
                target_object._skip_signals = False
        
        # Notify the creator
        if target_object and hasattr(target_object, 'created_by') and target_object.created_by:
            Notification.objects.create(
                recipient=target_object.created_by,
                notification_type='approval_action',
                title=f"Request Rejected: {approval_state.get_content_object_summary()}",
                message=(
                    f"Your request has been rejected.\n"
                    f"Request: {approval_state.get_content_object_summary()}\n"
                    f"Rejected by: {actor_user.get_full_name() or actor_user.username}\n"
                    f"Comments: {comment or 'No comments provided'}\n\n"
                    f"You can create a new request if needed."
                ),
                content_type=approval_state.content_type,
                object_id=str(approval_state.object_id),
                created_by=actor_user,
            )
        
        logger.info(f"Request {approval_state.object_id} rejected by {actor_user}")
        return approval_state
    
    @staticmethod
    @transaction.atomic
    def request_changes(approval_state, actor_user, comment):
        """
        Request changes on the current step, keeping it active for the requester to amend.
        
        Args:
            approval_state: The ApprovalState instance
            actor_user: The user requesting changes
            comment: Required comment explaining what changes are needed
        
        Returns:
            The updated ApprovalState instance
        
        Raises:
            ValidationError: If comment is empty
        """
        if not comment:
            raise ValidationError(_("Comment is required when requesting changes"))
        
        approval_state = ApprovalState.objects.select_for_update().get(pk=approval_state.pk)
        
        if not approval_state.actions_history:
            approval_state.actions_history = []
        
        current_step = approval_state.current_step
        if not current_step:
            raise ValidationError(_("No current step to request changes for"))
        
        # Record the action
        approval_state.actions_history.append({
            'action': 'changes_requested',
            'user_id': str(actor_user.id),
            'username': actor_user.username,
            'comment': comment,
            'timestamp': timezone.now().isoformat(),
            'step_id': str(current_step.id),
            'step_order': current_step.order,
        })
        approval_state.save(update_fields=['actions_history'])
        
        # Mark notifications as acted
        from django_4eyes.models import Notification
        Notification.objects.filter(
            content_type=approval_state.content_type,
            object_id=str(approval_state.object_id),
            step=current_step,
            notification_type='approval_required'
        ).update(
            acted=True,
            action_taken='changes_requested',
            updated_at=timezone.now()
        )
        
        # Notify the requester
        target_object = approval_state.content_object_unfiltered
        if target_object and hasattr(target_object, 'created_by') and target_object.created_by:
            requester = target_object.created_by
            Notification.objects.create(
                recipient=requester,
                notification_type='approval_action',
                title=f"Changes Requested: {approval_state.get_content_object_summary()}",
                message=(
                    f"Changes have been requested on your approval request.\n"
                    f"Request: {approval_state.get_content_object_summary()}\n"
                    f"Current Step: {current_step.title or f'Step {current_step.order}'}\n"
                    f"Requested by: {actor_user.get_full_name() or actor_user.username}\n"
                    f"Comments: {comment}\n\n"
                    f"Please make the requested changes and resubmit."
                ),
                content_type=approval_state.content_type,
                object_id=str(approval_state.object_id),
                step=current_step,
                created_by=actor_user,
            )
        
        logger.info(f"Changes requested for {approval_state.object_id} by {actor_user}")
        return approval_state
    
    @staticmethod
    @transaction.atomic
    def restart_approval_process(approval_state, actor_user, comment=None):
        """
        Restart the approval process after amendments.
        
        Args:
            approval_state: The ApprovalState instance to restart
            actor_user: The user restarting the process
            comment: Optional comment
        
        Returns:
            The updated ApprovalState instance
        """
        approval_state = ApprovalState.objects.select_for_update().select_related(
            'template', 'current_step', 'content_type'
        ).get(pk=approval_state.pk)
        
        # Determine which step to restart from
        restart_step = None
        
        if approval_state.has_pending_changes():
            # Restart from the step that requested changes
            changes_info = approval_state.get_pending_changes_info()
            if changes_info and changes_info.get('step_id'):
                try:
                    restart_step = ApprovalStep.objects.get(id=changes_info['step_id'])
                except ApprovalStep.DoesNotExist:
                    restart_step = approval_state.current_step
        elif approval_state.is_rejected:
            # Restart from the first step
            restart_step = approval_state.template.steps.filter(
                is_active=True
            ).order_by('order').first()
        
        if not restart_step:
            restart_step = approval_state.current_step
        
        if not restart_step:
            restart_step = approval_state.template.steps.filter(
                is_active=True
            ).order_by('order').first()
        
        if not restart_step:
            raise ValidationError(_("No active steps found in the approval template"))
        
        # Reset state
        approval_state.is_approved = False
        approval_state.is_rejected = False
        
        # Record restart action
        restart_action = {
            'action': 'restarted',
            'user_id': str(actor_user.id),
            'username': actor_user.username,
            'comment': comment or 'Process restarted after amendments',
            'timestamp': timezone.now().isoformat(),
            'step_id': str(restart_step.id),
            'step_order': restart_step.order,
        }
        
        if not approval_state.actions_history:
            approval_state.actions_history = []
        approval_state.actions_history.append(restart_action)
        
        approval_state.current_step = restart_step
        approval_state.save(
            update_fields=['is_approved', 'is_rejected', 'current_step', 'actions_history']
        )
        
        # Delete old notifications
        from django_4eyes.models import Notification
        Notification.objects.filter(
            content_type=approval_state.content_type,
            object_id=str(approval_state.object_id),
            notification_type='approval_required'
        ).delete()
        
        # Handle auto-approve or send notifications
        if restart_step.auto_approve:
            ApprovalWorkflowEngine._auto_approve_step(approval_state, restart_step)
        else:
            ApprovalWorkflowEngine._send_step_notifications(approval_state, restart_step)
        
        # Update target object
        target_object = approval_state.content_object_unfiltered
        if target_object:
            if hasattr(target_object, 'is_approved'):
                target_object.is_approved = False
                target_object.is_rejected = False
                try:
                    target_object._skip_signals = True
                    target_object.save(update_fields=['is_approved', 'is_rejected'])
                finally:
                    target_object._skip_signals = False
        
        logger.info(f"Approval {approval_state.pk} restarted from step {restart_step.order} by {actor_user}")
        return approval_state
    
    @staticmethod
    def _auto_approve_step(approval_state, step):
        """Auto-approve a step and move to the next one."""
        from django_4eyes.models import ApprovalStep, Notification
        
        # Record auto-approval
        if not approval_state.actions_history:
            approval_state.actions_history = []
        
        approval_state.actions_history.append({
            'action': 'approved',
            'step_id': str(step.id),
            'step_order': step.order,
            'user_id': None,
            'username': 'system',
            'comment': 'Auto-approved',
            'timestamp': timezone.now().isoformat()
        })
        
        # Find next step
        next_step = approval_state.template.steps.filter(
            order__gt=step.order
        ).first()
        
        if next_step:
            approval_state.current_step = next_step
            approval_state.save(update_fields=['current_step', 'actions_history'])
            
            if next_step.auto_approve:
                ApprovalWorkflowEngine._auto_approve_step(approval_state, next_step)
            else:
                ApprovalWorkflowEngine._send_step_notifications(approval_state, next_step)
        else:
            # All steps complete
            approval_state.is_approved = True
            approval_state.current_step = None
            approval_state.save(update_fields=['is_approved', 'current_step', 'actions_history'])
            
            target = approval_state.content_object_unfiltered
            if target:
                target.is_approved = True
                target.save(update_fields=['is_approved'])
            
            ApprovalWorkflowEngine._send_completion_notification(approval_state)
    
    @staticmethod
    def _send_step_notifications(approval_state, step):
        """Send notifications to approvers for a step using notification plugins."""
        from django_4eyes.models import Notification
        from django_4eyes.notifications import registry
        
        if step.auto_approve:
            return
        
        approvers = step.get_eligible_approvers()
        if not approvers:
            return
        
        obj_summary = approval_state.get_content_object_summary()
        obj_details = approval_state.get_content_object_details()
        
        notifications_data = []
        for approver in approvers:
            if not hasattr(approver, 'is_active') or not approver.is_active:
                continue
            
            message_lines = [
                f"Please review and take action on the following "
                f"{approval_state.get_content_type_display()}:",
                f"",
                f"Summary: {obj_summary}",
                f"Step: {step.title or f'Step {step.order}'}",
                f"Template: {approval_state.template.name}",
                f"",
                f"Object Details:"
            ]
            
            for key, value in obj_details.items():
                if key not in ['content_type', 'object_id', 'summary'] and value:
                    message_lines.append(f"- {key.replace('_', ' ').title()}: {value}")
            
            message_lines += [
                f"",
                f"Click the link below to view the full details and take action.",
                f"Required Action: {', '.join(step.get_available_actions(approver))}"
            ]
            
            title = f"Action Required: {obj_summary}"
            message = "\n".join(message_lines)
            
            # Store notification in database
            notifications_data.append({
                'recipient': approver,
                'notification_type': 'approval_required',
                'title': title,
                'message': message,
                'step': step,
                'content_type': approval_state.content_type,
                'object_id': str(approval_state.object_id),
            })
            
            # Send via notification plugins
            NotificationSender.send_to_user(
                recipient=approver,
                title=title,
                message=message,
                context={
                    'approval_state': approval_state,
                    'step': step,
                    'object_details': obj_details,
                }
            )
        
        # Bulk create notifications
        if notifications_data:
            Notification.objects.bulk_create(
                [Notification(**data) for data in notifications_data]
            )
    
    @staticmethod
    def _send_completion_notification(approval_state):
        """Send notification that approval is complete."""
        from django_4eyes.models import Notification
        
        target = approval_state.content_object_unfiltered
        if not target or not hasattr(target, 'created_by') or not target.created_by:
            return
        
        Notification.objects.create(
            recipient=target.created_by,
            notification_type='approval_completed',
            title=f"Approved: {approval_state.get_content_object_summary()}",
            message=(
                f"Your request has been fully approved.\n"
                f"Request: {approval_state.get_content_object_summary()}\n"
                f"Template: {approval_state.template.name}\n"
                f"Completed at: {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            ),
            content_type=approval_state.content_type,
            object_id=str(approval_state.object_id),
        )


# Import models for type hints (at end to avoid circular imports)
from django_4eyes.models import ApprovalState, ApprovalStep  # noqa: E402