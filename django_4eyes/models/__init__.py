
"""
Models for django-4eyes approval workflow engine.

This package contains all the models needed for the approval workflow system:
- FourEyeModel: Mixin to add approval capabilities to any model
- ApprovalTemplate: Defines reusable approval workflows
- ApprovalStep: Individual steps in an approval workflow
- ApprovalState: Tracks approval progress for specific objects
- Notification: Notifications for approvers
"""

from django_4eyes.models.base import (
    FourEyeModel,
    ApprovalMixin,
)
from django_4eyes.models.approval import (
    ApprovalTemplate,
    ApprovalStep,
    ApprovalState,
)
from django_4eyes.models.notification import Notification

__all__ = [
    'FourEyeModel',
    'ApprovalMixin',
    'ApprovalTemplate',
    'ApprovalStep',
    'ApprovalState',
    'Notification',
]