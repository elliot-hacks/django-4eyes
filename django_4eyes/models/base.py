"""
Base models and mixins for django-4eyes approval workflow engine.
"""

import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ApprovalAwareQuerySet(models.QuerySet):
    """
    Custom QuerySet that filters objects based on approval status.
    
    By default, only approved objects are visible through the main manager.
    Use the 'all_objects' manager to access all objects including pending/rejected.
    """
    
    def approved(self):
        """Return only approved objects."""
        return self.filter(is_approved=True, is_rejected=False)
    
    def pending(self):
        """Return only pending objects (not yet approved or rejected)."""
        return self.filter(is_approved=False, is_rejected=False)
    
    def rejected(self):
        """Return only rejected objects."""
        return self.filter(is_rejected=True)
    
    def visible(self):
        """
        Return objects that are safe to show to end users.
        
        For models with active approval templates, only approved objects are shown.
        For models without templates, all objects are shown.
        """
        from django.contrib.contenttypes.models import ContentType
        from django_4eyes.models import ApprovalTemplate
        
        # Check if this model has an active approval template
        try:
            ct = ContentType.objects.get_for_model(self.model)
            has_template = ApprovalTemplate.objects.filter(
                content_type=ct,
                is_active=True
            ).exists()
            
            if has_template:
                return self.filter(is_approved=True, is_rejected=False)
        except Exception:
            pass
        
        return self


class ApprovalAwareManager(models.Manager):
    """
    Default manager for FourEyeModel that only shows approved objects.
    
    External callers (views, serializers, FK traversals) automatically
    receive only the records they are allowed to see.
    
    Internal callers (approval engine, admin) should use ``Model.all_objects``
    to bypass the filter entirely.
    """
    
    def get_queryset(self):
        return ApprovalAwareQuerySet(self.model, using=self._db).visible()
    
    def approved(self):
        return self.get_queryset().approved()
    
    def pending(self):
        """All pending records — bypasses the visibility gate."""
        return ApprovalAwareQuerySet(self.model, using=self._db).pending()
    
    def rejected(self):
        """All rejected records — bypasses the visibility gate."""
        return ApprovalAwareQuerySet(self.model, using=self._db).rejected()


class ApprovalMixin(models.Model):
    """
    Mixin to add approval capabilities to any model.
    
    This mixin adds:
    - is_approved: Boolean field indicating approval status
    - is_rejected: Boolean field indicating rejection status
    - objects: Manager that only shows approved objects
    - all_objects: Manager that shows all objects
    
    Usage:
        class MyModel(FourEyeModel, models.Model):
            # your fields here
            pass
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for this record")
    )
    is_approved = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("Whether this record has been approved")
    )
    is_rejected = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("Whether this record has been rejected")
    )
    
    # Custom managers
    objects = ApprovalAwareManager()
    all_objects = models.Manager()
    
    class Meta:
        abstract = True
    
    def clean(self):
        """Validate approval state."""
        super().clean()
        self.validate_approval()
    
    def validate_approval(self):
        """Validate that object cannot be both approved and rejected."""
        if self.is_approved and self.is_rejected:
            raise ValidationError(
                _("An object cannot be both approved and rejected.")
            )
    
    def __init__(self, *args, **kwargs):
        """Initialize with transient fields."""
        self._update_reason = None  # transient, never persisted
        self._skip_signals = False  # flag to skip signal handlers
        super().__init__(*args, **kwargs)
    
    def __str__(self):
        """String representation."""
        status = "Approved" if self.is_approved else "Rejected" if self.is_rejected else "Pending"
        return f"{self.__class__.__name__} ({status})"


class FourEyeModel(ApprovalMixin):
    """
    Complete model with approval capabilities.
    
    This is the main model to inherit from when you want to add approval
    workflow to your Django model.
    
    Example:
        class PurchaseRequest(FourEyeModel, models.Model):
            title = models.CharField(max_length=200)
            amount = models.DecimalField(max_digits=10, decimal_places=2)
            created_by = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    """
    
    class Meta:
        abstract = True
        ordering = ['-id']