"""
Tests for django-4eyes notification plugins (email, django messages),
the sender coordinator, and the plugin registry.
"""

from unittest.mock import patch

from django.contrib import messages as django_messages
from django.contrib.auth.models import User, Group
from django.core import mail
from django.test import TestCase, override_settings

from django_4eyes.notifications.base import (
    NotificationPlugin,
    NotificationPluginRegistry,
)
from django_4eyes.notifications.django_messages import DjangoMessagesNotificationPlugin
from django_4eyes.notifications.email import EmailNotificationPlugin
from django_4eyes.notifications.registry import registry
from django_4eyes.notifications.sender import NotificationSender


class TestEmailNotificationPlugin(TestCase):
    """Test the EmailNotificationPlugin."""

    def setUp(self):
        self.plugin = EmailNotificationPlugin()
        self.user = User.objects.create_user(
            'alice', 'alice@example.com', 'password'
        )
        mail.outbox = []

    def test_send_plain_email(self):
        """Sending with no matching template falls back to plain text."""
        result = self.plugin.send(
            recipient=self.user,
            title="Approval needed",
            message="Please review this request",
        )
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

        sent = mail.outbox[0]
        self.assertEqual(sent.subject, "Approval needed")
        self.assertEqual(sent.body, "Please review this request")
        self.assertEqual(sent.to, ["alice@example.com"])
        self.assertEqual(sent.from_email, "approvals@example.com")

    def test_foureyes_email_from_takes_precedence(self):
        """FOUREYES_EMAIL_FROM should be preferred over DEFAULT_FROM_EMAIL."""
        with override_settings(
            FOUREYES_EMAIL_FROM='workflow@example.com',
            DEFAULT_FROM_EMAIL='default@example.com',
        ):
            self.plugin.send(
                recipient=self.user, title="Hi", message="Body"
            )
        self.assertEqual(mail.outbox[0].from_email, "workflow@example.com")

    def test_falls_back_to_default_from_email(self):
        """When FOUREYES_EMAIL_FROM is unset, DEFAULT_FROM_EMAIL is used."""
        with override_settings(
            FOUREYES_EMAIL_FROM=None,
            DEFAULT_FROM_EMAIL='default@example.com',
        ):
            self.plugin.send(
                recipient=self.user, title="Hi", message="Body"
            )
        self.assertEqual(mail.outbox[0].from_email, "default@example.com")

    def test_no_from_email_configured(self):
        """Send should fail cleanly if no from-email is configured anywhere."""
        with override_settings(FOUREYES_EMAIL_FROM=None, DEFAULT_FROM_EMAIL=None):
            result = self.plugin.send(
                recipient=self.user, title="Hi", message="Body"
            )
        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    def test_recipient_without_email(self):
        """Users with no email address should not receive mail."""
        user = User.objects.create_user('noemail', '', 'password')
        result = self.plugin.send(recipient=user, title="Hi", message="Body")
        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_recipient(self):
        """Inactive users should not receive mail."""
        self.user.is_active = False
        self.user.save()
        result = self.plugin.send(
            recipient=self.user, title="Hi", message="Body"
        )
        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    def test_send_failure_is_caught(self):
        """Errors raised by the mail backend should not propagate."""
        with patch(
            'django_4eyes.notifications.email.send_mail',
            side_effect=Exception("SMTP down"),
        ):
            result = self.plugin.send(
                recipient=self.user, title="Hi", message="Body"
            )
        self.assertFalse(result)

    def test_html_template_used_when_present(self):
        """When an HTML template exists it should be used over plain text."""
        with patch.object(
            self.plugin, '_render_email_template', return_value='<p>Hi</p>'
        ):
            result = self.plugin.send(
                recipient=self.user, title="Hi", message="Plain body"
            )
        self.assertTrue(result)
        sent = mail.outbox[0]
        self.assertEqual(len(sent.alternatives), 1)
        html_body, mimetype = sent.alternatives[0]
        self.assertEqual(html_body, '<p>Hi</p>')
        self.assertEqual(mimetype, 'text/html')
        self.assertEqual(sent.body, 'Plain body')

    def test_can_send_true_for_active_user_with_email(self):
        self.assertTrue(self.plugin.can_send(self.user))

    def test_can_send_false_without_email(self):
        user = User.objects.create_user('noemail2', '', 'password')
        self.assertFalse(self.plugin.can_send(user))

    def test_can_send_false_for_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        self.assertFalse(self.plugin.can_send(self.user))

    def test_can_send_respects_user_preference_flag(self):
        self.user.email_notifications_enabled = False
        self.assertFalse(self.plugin.can_send(self.user))


class TestDjangoMessagesNotificationPlugin(TestCase):
    """Test the DjangoMessagesNotificationPlugin."""

    def setUp(self):
        self.plugin = DjangoMessagesNotificationPlugin()
        self.user = User.objects.create_user(
            'bob', 'bob@example.com', 'password'
        )

    def test_send_queues_message_for_user(self):
        result = self.plugin.send(
            recipient=self.user, title="Approval needed", message="Please review"
        )
        self.assertTrue(result)

        queued = DjangoMessagesNotificationPlugin.get_messages_for_user(self.user)
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]['message'], "Approval needed\nPlease review")
        self.assertEqual(queued[0]['level'], django_messages.INFO)

    def test_send_uses_requested_level(self):
        self.plugin.send(
            recipient=self.user, title="Uh oh", message="Something failed",
            level='error',
        )
        queued = DjangoMessagesNotificationPlugin.get_messages_for_user(self.user)
        self.assertEqual(queued[0]['level'], django_messages.ERROR)

    def test_get_messages_for_user_drains_by_default(self):
        self.plugin.send(recipient=self.user, title="Hi", message="Body")
        first = DjangoMessagesNotificationPlugin.get_messages_for_user(self.user)
        second = DjangoMessagesNotificationPlugin.get_messages_for_user(self.user)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_get_messages_for_user_can_peek_without_clearing(self):
        self.plugin.send(recipient=self.user, title="Hi", message="Body")
        first = DjangoMessagesNotificationPlugin.get_messages_for_user(
            self.user, clear=False
        )
        second = DjangoMessagesNotificationPlugin.get_messages_for_user(self.user)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)

    def test_messages_are_isolated_per_user(self):
        other = User.objects.create_user('carol', 'carol@example.com', 'password')
        self.plugin.send(recipient=self.user, title="For bob", message="")
        self.assertEqual(
            len(DjangoMessagesNotificationPlugin.get_messages_for_user(other)), 0
        )
        self.assertEqual(
            len(DjangoMessagesNotificationPlugin.get_messages_for_user(self.user)), 1
        )

    def test_can_send_false_for_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        self.assertFalse(self.plugin.can_send(self.user))

    def test_can_send_respects_user_preference_flag(self):
        self.user.django_messages_enabled = False
        self.assertFalse(self.plugin.can_send(self.user))


class TestNotificationPluginRegistry(TestCase):
    """Test the NotificationPluginRegistry class in isolation."""

    def setUp(self):
        self.registry = NotificationPluginRegistry()

        class FakePluginA(NotificationPlugin):
            plugin_id = 'fake_a'
            name = 'Fake A'
            enabled_by_default = True

            def send(self, recipient, title, message, context=None, **kwargs):
                return True

        class FakePluginB(NotificationPlugin):
            plugin_id = 'fake_b'
            name = 'Fake B'
            enabled_by_default = False

            def send(self, recipient, title, message, context=None, **kwargs):
                return True

        self.plugin_a = FakePluginA()
        self.plugin_b = FakePluginB()

    def test_register_and_get(self):
        self.registry.register(self.plugin_a)
        self.assertIs(self.registry.get('fake_a'), self.plugin_a)

    def test_register_requires_plugin_id(self):
        class NoIdPlugin(NotificationPlugin):
            plugin_id = ''

            def send(self, recipient, title, message, context=None, **kwargs):
                return True

        with self.assertRaises(ValueError):
            self.registry.register(NoIdPlugin())

    def test_unregister(self):
        self.registry.register(self.plugin_a)
        self.registry.unregister('fake_a')
        self.assertIsNone(self.registry.get('fake_a'))

    def test_unregister_unknown_id_is_a_noop(self):
        self.registry.unregister('does_not_exist')  # should not raise

    def test_get_all(self):
        self.registry.register(self.plugin_a)
        self.registry.register(self.plugin_b)
        self.assertEqual(set(self.registry.get_all()), {self.plugin_a, self.plugin_b})

    def test_is_registered(self):
        self.registry.register(self.plugin_a)
        self.assertTrue(self.registry.is_registered('fake_a'))
        self.assertFalse(self.registry.is_registered('fake_b'))

    def test_clear(self):
        self.registry.register(self.plugin_a)
        self.registry.clear()
        self.assertEqual(self.registry.get_all(), [])

    def test_get_enabled_defaults_to_enabled_by_default_flag(self):
        self.registry.register(self.plugin_a)
        self.registry.register(self.plugin_b)
        enabled = self.registry.get_enabled()
        self.assertIn(self.plugin_a, enabled)
        self.assertNotIn(self.plugin_b, enabled)

    def test_get_enabled_respects_settings_override(self):
        self.registry.register(self.plugin_a)
        self.registry.register(self.plugin_b)
        with override_settings(FOUREYES_ENABLED_NOTIFICATION_PLUGINS=['fake_b']):
            enabled = self.registry.get_enabled()
        self.assertEqual(enabled, [self.plugin_b])


class TestGlobalRegistryDefaults(TestCase):
    """The global registry auto-registers the built-in plugins on import."""

    def test_email_and_django_messages_are_registered(self):
        self.assertTrue(registry.is_registered('email'))
        self.assertTrue(registry.is_registered('django_messages'))
        self.assertIsInstance(registry.get('email'), EmailNotificationPlugin)
        self.assertIsInstance(
            registry.get('django_messages'), DjangoMessagesNotificationPlugin
        )


class TestNotificationSender(TestCase):
    """Test the NotificationSender coordinator."""

    def setUp(self):
        self.user = User.objects.create_user(
            'dave', 'dave@example.com', 'password'
        )
        mail.outbox = []

    def test_send_to_user_runs_all_enabled_plugins(self):
        results = NotificationSender.send_to_user(
            recipient=self.user, title="Approval needed", message="Please review"
        )
        self.assertEqual(results, {'email': True, 'django_messages': True})
        self.assertEqual(len(mail.outbox), 1)

    def test_send_to_user_can_restrict_to_specific_plugins(self):
        results = NotificationSender.send_to_user(
            recipient=self.user,
            title="Approval needed",
            message="Please review",
            plugins=['email'],
        )
        self.assertEqual(results, {'email': True})
        self.assertEqual(len(mail.outbox), 1)

    def test_send_to_user_skips_plugin_when_can_send_is_false(self):
        results = NotificationSender.send_to_user(
            recipient=self.user,
            title="Hi",
            message="Body",
            plugins=['email'],
        )
        self.user.is_active = False
        self.user.save()
        results = NotificationSender.send_to_user(
            recipient=self.user,
            title="Hi",
            message="Body",
            plugins=['email'],
        )
        self.assertEqual(results, {'email': False})

    def test_send_to_user_handles_plugin_exception_gracefully(self):
        with patch.object(
            EmailNotificationPlugin, 'send', side_effect=Exception("boom")
        ):
            results = NotificationSender.send_to_user(
                recipient=self.user,
                title="Hi",
                message="Body",
                plugins=['email'],
            )
        self.assertEqual(results, {'email': False})

    def test_send_to_users(self):
        other = User.objects.create_user('erin', 'erin@example.com', 'password')
        results = NotificationSender.send_to_users(
            recipients=[self.user, other],
            title="Hi",
            message="Body",
            plugins=['email'],
        )
        self.assertEqual(results['email'][self.user], True)
        self.assertEqual(results['email'][other], True)
        self.assertEqual(len(mail.outbox), 2)

    def test_send_to_group_only_notifies_active_members(self):
        group = Group.objects.create(name="Approvers")
        inactive = User.objects.create_user(
            'frank', 'frank@example.com', 'password', is_active=False
        )
        self.user.groups.add(group)
        inactive.groups.add(group)

        results = NotificationSender.send_to_group(
            group=group, title="Hi", message="Body", plugins=['email']
        )
        self.assertIn(self.user, results['email'])
        self.assertNotIn(inactive, results['email'])
        self.assertEqual(len(mail.outbox), 1)

    def test_get_available_plugins_lists_all_registered(self):
        available = {p['plugin_id'] for p in NotificationSender.get_available_plugins()}
        self.assertEqual(available, {'email', 'django_messages'})

    def test_get_enabled_plugins_respects_settings(self):
        with override_settings(FOUREYES_ENABLED_NOTIFICATION_PLUGINS=['email']):
            enabled = {p['plugin_id'] for p in NotificationSender.get_enabled_plugins()}
        self.assertEqual(enabled, {'email'})
