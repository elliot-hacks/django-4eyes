"""
Tests for django-4eyes models.
"""

import uuid
from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from django_4eyes.models import (
    FourEyeModel,
    ApprovalTemplate,
    ApprovalStep,
    ApprovalState,
    Notification,
)


class TestApprovalMixin(TestCase):
    """Test the ApprovalMixin and FourEyeModel."""
    
    def test_four_eye_model_has_required_fields(self):
        """Test that FourEyeModel adds required fields."""
        from django_4eyes.models.base import ApprovalMixin
        
        # ApprovalMixin should have these field definitions
        self.assertTrue(hasattr(ApprovalMixin, 'is_approved'))
        self.assertTrue(hasattr(ApprovalMixin, 'is_rejected'))
        
        # Check that the managers are defined in the class
        self.assertIn('objects', ApprovalMixin.__dict__)
        self.assertIn('all_objects', ApprovalMixin.__dict__)
    
    def test_approval_mixin_validation(self):
        """Test that object cannot be both approved and rejected."""
        # This is tested via the clean() method
        from django_4eyes.models.base import ApprovalMixin
        
        # Create a mock instance
        class MockModel(ApprovalMixin):
            class Meta:
                app_label = 'test'
        
        instance = MockModel(is_approved=True, is_rejected=True)
        with self.assertRaises(ValidationError):
            instance.clean()


class TestApprovalTemplate(TestCase):
    """Test the ApprovalTemplate model."""
    
    def test_create_template(self):
        """Test creating an approval template."""
        template = ApprovalTemplate.objects.create(
            name="Test Template",
            description="A test approval template"
        )
        self.assertEqual(str(template), "Test Template ()")
        self.assertTrue(template.is_active)
        self.assertTrue(template.auto_start_approval)
    
    def test_template_with_content_type(self):
        """Test assigning content types to template."""
        template = ApprovalTemplate.objects.create(
            name="User Template"
        )
        user_ct = ContentType.objects.get_for_model(User)
        template.content_type.add(user_ct)
        
        self.assertIn(user_ct, template.content_type.all())


class TestApprovalStep(TestCase):
    """Test the ApprovalStep model."""
    
    def setUp(self):
        self.template = ApprovalTemplate.objects.create(name="Test Template")
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password')
        self.group = Group.objects.create(name="Approvers")
    
    def test_create_step_with_user(self):
        """Test creating a step with a specific user."""
        step = ApprovalStep.objects.create(
            template=self.template,
            order=1,
            title="Manager Approval",
            approver_user=self.user
        )
        self.assertEqual(str(step), "Test Template - Step 1: Manager Approval")
        self.assertTrue(step.can_user_approve(self.user))
    
    def test_create_step_with_group(self):
        """Test creating a step with a group."""
        step = ApprovalStep.objects.create(
            template=self.template,
            order=2,
            approver_group=self.group
        )
        self.user.groups.add(self.group)
        self.assertTrue(step.can_user_approve(self.user))
    
    def test_auto_approve_step(self):
        """Test auto-approve step allows anyone."""
        step = ApprovalStep.objects.create(
            template=self.template,
            order=3,
            auto_approve=True
        )
        # Auto-approve steps should allow any authenticated user
        self.assertTrue(step.can_user_approve(self.user))
    
    def test_step_validation_requires_approver(self):
        """Test that step requires an approver or auto_approve."""
        step = ApprovalStep(
            template=self.template,
            order=4
        )
        with self.assertRaises(ValidationError):
            step.clean()
    
    def test_get_available_actions(self):
        """Test getting available actions for a step."""
        step = ApprovalStep.objects.create(
            template=self.template,
            order=1,
            approver_user=self.user,
            allow_comments=True
        )
        actions = step.get_available_actions(self.user)
        self.assertIn('approve', actions)
        self.assertIn('reject', actions)
        self.assertIn('request_changes', actions)


class TestApprovalState(TestCase):
    """Test the ApprovalState model."""
    
    def setUp(self):
        self.template = ApprovalTemplate.objects.create(name="Test Template")
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password')
        self.step = ApprovalStep.objects.create(
            template=self.template,
            order=1,
            approver_user=self.user
        )
        self.content_type = ContentType.objects.get_for_model(User)
    
    def test_create_approval_state(self):
        """Test creating an approval state."""
        state = ApprovalState.objects.create(
            content_type=self.content_type,
            object_id=uuid.uuid4(),
            template=self.template,
            current_step=self.step
        )
        self.assertFalse(state.is_approved)
        self.assertFalse(state.is_rejected)
        self.assertTrue(state.is_pending_approval())
    
    def test_approval_progress(self):
        """Test calculating approval progress."""
        state = ApprovalState.objects.create(
            content_type=self.content_type,
            object_id=uuid.uuid4(),
            template=self.template,
            current_step=self.step
        )
        # No steps completed yet
        self.assertEqual(state.get_approval_progress(), 0)
    
    def test_can_user_take_action(self):
        """Test checking if user can take action."""
        state = ApprovalState.objects.create(
            content_type=self.content_type,
            object_id=uuid.uuid4(),
            template=self.template,
            current_step=self.step
        )
        self.assertTrue(state.can_user_take_action(self.user))
        
        # After approval, user cannot take action
        state.is_approved = True
        state.current_step = None
        self.assertFalse(state.can_user_take_action(self.user))
    
    def test_has_pending_changes(self):
        """Test checking for pending changes."""
        state = ApprovalState.objects.create(
            content_type=self.content_type,
            object_id=uuid.uuid4(),
            template=self.template,
            current_step=self.step,
            actions_history=[
                {'action': 'changes_requested', 'username': 'approver'}
            ]
        )
        self.assertTrue(state.has_pending_changes())
        
        # After restart, no pending changes
        state.actions_history.append({'action': 'restarted', 'username': 'user'})
        state.save()
        self.assertFalse(state.has_pending_changes())


class TestNotification(TestCase):
    """Test the Notification model."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password')
    
    def test_create_notification(self):
        """Test creating a notification."""
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type='approval_required',
            title="Please approve this request"
        )
        self.assertFalse(notification.is_read)
        self.assertFalse(notification.acted)
    
    def test_mark_as_read(self):
        """Test marking notification as read."""
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type='approval_required',
            title="Test"
        )
        notification.mark_as_read()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)
    
    def test_mark_as_acted(self):
        """Test marking notification as acted."""
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type='approval_required',
            title="Test"
        )
        notification.mark_as_acted('approved', "Looks good!")
        self.assertTrue(notification.acted)
        self.assertEqual(notification.action_taken, 'approved')