"""
Approval workflow models for django-4eyes.

Contains:
- ApprovalTemplate: Defines reusable approval workflows
- ApprovalStep: Individual steps in an approval workflow
- ApprovalState: Tracks approval progress for specific objects
"""

from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from functools import lru_cache


class ApprovalTemplateQuerySet(models.QuerySet):
    """Custom QuerySet for ApprovalTemplate with optimizations."""
    
    def optimized(self):
        """Return optimized queryset with prefetching."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        return (
            self.select_related('created_by', 'updated_by')
            .prefetch_related(
                # Prefetch content types
                'content_type',
                # Prefetch steps with approvers
                models.Prefetch(
                    'steps',
                    queryset=ApprovalStep.objects
                        .select_related('approver_user', 'approver_group')
                        .prefetch_related(
                            models.Prefetch(
                                'approver_group__user_set',
                                queryset=User.objects.only('id', 'username'),
                                to_attr='prefetched_group_users'
                            )
                        ),
                    to_attr='prefetched_steps'
                ),
            )
        )


class ApprovalTemplateManager(models.Manager):
    """Custom manager for ApprovalTemplate."""
    
    def get_queryset(self):
        return ApprovalTemplateQuerySet(self.model, using=self._db)
    
    def optimized(self):
        return self.get_queryset().optimized()
    
    @lru_cache(maxsize=256)
    def get_by_natural_key(self, name):
        return self.get(name=name)


class ApprovalTemplate(models.Model):
    """
    Defines a reusable approval workflow template.
    
    An approval template specifies the steps required to approve an object.
    Templates can be assigned to models via ContentType.
    
    Example:
        template = ApprovalTemplate.objects.create(
            name="Purchase Request Approval",
            description="Standard workflow for purchase requests",
            is_active=True,
            auto_start_approval=True
        )
        template.content_type.add(ContentType.objects.get_for_model(PurchaseRequest))
    """
    
    name = models.CharField(
        max_length=100,
        help_text=_("Name of this approval template")
    )
    description = models.TextField(
        blank=True,
        help_text=_("Description of when this template should be used")
    )
    content_type = models.ManyToManyField(
        ContentType,
        help_text=_("Which model types this template applies to")
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether this template is currently active")
    )
    auto_start_approval = models.BooleanField(
        default=True,
        help_text=_("Automatically start approval process when object is created")
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='created_approval_templates'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='updated_approval_templates'
    )
    
    objects = ApprovalTemplateManager()
    all_objects = models.Manager()
    
    class Meta:
        verbose_name = _("Approval Template")
        verbose_name_plural = _("Approval Templates")
        ordering = ['-created_at']
    
    def __str__(self):
        ct_names = ", ".join([ct.model for ct in self.content_type.all()])
        return f"{self.name} ({ct_names})"
    
    def natural_key(self):
        return (self.name,)
    
    def get_steps_for_object(self, obj):
        """Get approval steps ordered for a specific object."""
        return self.steps.all().order_by('order')
    
    def clean(self):
        """Validate template configuration."""
        super().clean()
        if not self.content_type.exists():
            raise ValidationError(_("Template must be assigned to at least one model."))


class ApprovalStep(models.Model):
    """
    Individual step in an approval workflow.
    
    Each step specifies who can approve (user or group) and whether
    the step can be auto-approved.
    
    Example:
        step = ApprovalStep.objects.create(
            template=template,
            order=1,
            title="Manager Approval",
            approver_group=manager_group,
            allow_comments=True
        )
    """
    
    template = models.ForeignKey(
        ApprovalTemplate,
        on_delete=models.CASCADE,
        related_name='steps',
        help_text=_("The template this step belongs to")
    )
    order = models.PositiveIntegerField(
        help_text=_("Order of this step (1-based, lower numbers first)")
    )
    title = models.CharField(
        max_length=150,
        blank=True,
        help_text=_("Human-readable title for this step")
    )
    approver_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_("Specific user who can approve this step")
    )
    approver_group = models.ForeignKey(
        'auth.Group',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_("Group whose members can approve this step")
    )
    can_edit = models.BooleanField(
        default=False,
        help_text=_("Whether approver can edit the object during approval")
    )
    allow_comments = models.BooleanField(
        default=False,
        help_text=_("Whether approver can add comments")
    )
    auto_approve = models.BooleanField(
        default=False,
        help_text=_("If enabled, this step is auto-approved without user action")
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Approval Step")
        verbose_name_plural = _("Approval Steps")
        ordering = ['template', 'order']
        unique_together = ('template', 'order')
    
    def __str__(self):
        # Build approver description
        if self.approver_user:
            who = f"User: {self.approver_user.get_full_name() or self.approver_user.username}"
        elif self.approver_group:
            who = f"Group: {self.approver_group.name}"
        else:
            who = "Unassigned"
        
        auto = " (Auto)" if self.auto_approve else ""
        title = self.title or who
        
        return f"{self.template.name} - Step {self.order}: {title}{auto}"
    
    def clean(self):
        """Validate that at least one approver is set or auto_approve is True."""
        super().clean()
        if not self.auto_approve and not self.approver_group and not self.approver_user:
            raise ValidationError(
                _("Either set an approver group, approver user, or enable auto-approve.")
            )
    
    def get_available_actions(self, user):
        """Get available actions for this step based on user permissions."""
        if not user or not user.is_authenticated:
            return []
        
        if not self.can_user_approve(user):
            return []
        
        actions = ['approve', 'reject']
        if self.allow_comments:
            actions.append('request_changes')
        
        return actions
    
    def can_user_approve(self, user):
        """Check if user can approve this step."""
        if not user or not user.is_authenticated:
            return False
        
        if self.auto_approve:
            return True
        
        # Check superuser override
        if user.is_superuser and getattr(settings, 'APPROVAL_ALLOW_SUPERUSER_OVERRIDE', True):
            return True
        
        # Check specific user
        if self.approver_user_id == user.id:
            return True
        
        # Check group membership (use prefetched if available)
        if hasattr(self.approver_group, "prefetched_group_users"):
            return any(u.id == user.id for u in self.approver_group.prefetched_group_users)
        
        # Fallback to query
        return self.approver_group.user_set.filter(id=user.id).exists()
    
    def get_eligible_approvers(self):
        """Get all users who can approve this step."""
        approvers = set()
        
        if self.approver_user:
            approvers.add(self.approver_user)
        
        # Use prefetched users if available
        if hasattr(self.approver_group, "prefetched_group_users"):
            approvers.update(self.approver_group.prefetched_group_users)
        elif self.approver_group:
            approvers.update(self.approver_group.user_set.all())
        
        # Add superusers if allowed
        if getattr(settings, 'APPROVAL_ALLOW_SUPERUSER_OVERRIDE', True):
            from django.contrib.auth import get_user_model
            User = get_user_model()
            superusers = User.objects.filter(is_superuser=True).only('id', 'username')
            approvers.update(superusers)
        
        return list(approvers)


class ApprovalState(models.Model):
    """
    Tracks approval state for a specific object.
    
    Each object that requires approval has an ApprovalState that tracks
    the current step, history of actions, and overall status.
    
    Example:
        # Get approval state for an object
        state = ApprovalState.objects.get(
            content_type=ContentType.objects.get_for_model(MyModel),
            object_id=my_object.pk
        )
        
        # Check if user can take action
        if state.can_user_take_action(user):
            state = ApprovalWorkflowEngine.advance_approval(state, user)
    """
    
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text=_("Type of the object being approved")
    )
    object_id = models.UUIDField(
        help_text=_("ID of the object being approved")
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    template = models.ForeignKey(
        ApprovalTemplate,
        on_delete=models.CASCADE,
        help_text=_("The approval template being used")
    )
    current_step = models.ForeignKey(
        ApprovalStep,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        help_text=_("Current step in the approval process")
    )
    
    is_approved = models.BooleanField(
        default=False,
        help_text=_("Whether the object has been fully approved")
    )
    is_rejected = models.BooleanField(
        default=False,
        help_text=_("Whether the object has been rejected")
    )
    
    actions_history = models.JSONField(
        default=list,
        blank=True,
        help_text=_("History of all actions taken during approval")
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='created_approval_states'
    )
    
    class Meta:
        verbose_name = _("Approval State")
        verbose_name_plural = _("Approval States")
        unique_together = (('content_type', 'object_id', 'template'),)
        ordering = ['-created_at']
    
    def __str__(self):
        obj = self.content_object_unfiltered
        return f"Approval for {obj} - {self.template.name}"
    
    @property
    def content_object_unfiltered(self):
        """
        Retrieve the linked content object, bypassing any approval-gating manager.
        
        Use this inside the approval engine where the object may still be pending.
        """
        if not self.content_type_id or not self.object_id:
            return None
        
        model_class = self.content_type.model_class()
        if model_class is None:
            return None
        
        # Use all_objects manager if available, otherwise default
        manager = getattr(model_class, 'all_objects', model_class._default_manager)
        
        try:
            return manager.get(pk=self.object_id)
        except model_class.DoesNotExist:
            return None
    
    def can_user_take_action(self, user):
        """Check if user can take action on current step."""
        if self.is_approved or self.is_rejected:
            return False
        if not self.current_step:
            return False
        return self.current_step.can_user_approve(user)
    
    def has_pending_changes(self):
        """Check if changes were requested for this approval."""
        if not self.actions_history:
            return False
        
        has_changes_requested = False
        for action in reversed(self.actions_history):
            if action.get('action') == 'changes_requested':
                has_changes_requested = True
            elif action.get('action') in ['restarted', 'approved']:
                has_changes_requested = False
                break
        
        return has_pending_changes
    
    def get_pending_changes_info(self):
        """Get information about pending changes."""
        if not self.has_pending_changes():
            return None
        
        for action in reversed(self.actions_history or []):
            if action.get('action') == 'changes_requested':
                return {
                    'requested_by': action.get('username'),
                    'comment': action.get('comment'),
                    'timestamp': action.get('timestamp'),
                }
        return None
    
    def get_current_approvers(self):
        """Get users who can approve the current step."""
        if not self.current_step:
            return []
        return self.current_step.get_eligible_approvers()
    
    def get_approval_progress(self):
        """Get approval progress percentage."""
        total_steps = self.template.steps.count()
        if total_steps == 0:
            return 0
        
        completed_steps = len([
            a for a in (self.actions_history or [])
            if a.get('action') == 'approved'
        ])
        return int((completed_steps / total_steps) * 100)
    
    def is_pending_approval(self):
        """Check if object is pending approval."""
        return not self.is_approved and not self.is_rejected and self.current_step
    
    def get_content_type_display(self):
        """Get human-readable content type name."""
        if self.content_type:
            try:
                return self.content_type.model_class()._meta.verbose_name.title()
            except Exception:
                pass
        return "Unknown"
    
    def get_content_object_summary(self):
        """Get a summary of the object being approved."""
        if not self.content_object_unfiltered:
            return "No content object"
        
        obj = self.content_object_unfiltered
        summary_parts = []
        
        # Try common fields
        for field in ['number', 'title', 'name', 'subject']:
            if hasattr(obj, field) and getattr(obj, field):
                summary_parts.append(str(getattr(obj, field)))
                break
        
        if not summary_parts:
            summary_parts.append(str(obj))
        
        return " - ".join(summary_parts)
    
    def get_content_object_details(self):
        """Get detailed information about the object for approvers."""
        if not self.content_object_unfiltered:
            return {}
        
        obj = self.content_object_unfiltered
        details = {
            'content_type': self.get_content_type_display(),
            'object_id': str(obj.pk),
            'summary': self.get_content_object_summary(),
        }
        
        # Add common fields
        common_fields = ['description', 'total_amount', 'created_by', 'created_at', 'status']
        for field in common_fields:
            if hasattr(obj, field):
                value = getattr(obj, field)
                if value:
                    details[field] = str(value)
        
        return details
    
    def restart_approval_process(self, user, comment=None):
        """Restart the approval process."""
        from django_4eyes.engine import ApprovalWorkflowEngine
        return ApprovalWorkflowEngine.restart_approval_process(self, user, comment)