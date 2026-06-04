"""
Email notification plugin for django-4eyes.
"""

import logging
from typing import Dict, Any, Optional
from django.contrib.auth.models import User
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags

from django_4eyes.notifications.base import NotificationPlugin

logger = logging.getLogger(__name__)


class EmailNotificationPlugin(NotificationPlugin):
    """
    Email notification plugin.
    
    Sends approval notifications via email using Django's email backend.
    Supports HTML email templates and configurable email settings.
    """
    
    plugin_id = 'email'
    name = 'Email Notification'
    description = 'Send approval notifications via email'
    enabled_by_default = True
    
    def send(
        self,
        recipient: User,
        title: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> bool:
        """
        Send an email notification.
        
        Args:
            recipient: User to send email to
            title: Email subject
            message: Email body
            context: Additional context for template rendering
            **kwargs: Additional arguments
            
        Returns:
            True if email was sent successfully
        """
        # Check if user has email
        if not recipient.email:
            logger.warning(f"User {recipient.username} has no email address")
            return False
        
        # Check if user is active
        if not recipient.is_active:
            return False
        
        try:
            # Get email settings
            from_email = self._get_from_email()
            if not from_email:
                logger.error("No FROM_EMAIL configured for django-4eyes")
                return False
            
            # Prepare email context
            email_context = self.get_template_context(title, message, context)
            email_context['recipient'] = recipient
            email_context['site_name'] = getattr(settings, 'SITE_NAME', 'Django Application')
            
            # Try to render HTML template if it exists
            html_content = self._render_email_template('email', email_context)
            
            if html_content:
                # Send HTML email
                return self._send_html_email(
                    recipient=recipient,
                    subject=title,
                    html_content=html_content,
                    text_content=strip_tags(message),
                    from_email=from_email
                )
            else:
                # Send plain text email
                return self._send_plain_email(
                    recipient=recipient,
                    subject=title,
                    message=message,
                    from_email=from_email
                )
                
        except Exception as e:
            logger.error(f"Failed to send email to {recipient.email}: {e}", exc_info=True)
            return False
    
    def _get_from_email(self) -> Optional[str]:
        """Get the from email address from settings."""
        # Check for django-4eyes specific setting
        from_email = getattr(settings, 'FOUREYES_EMAIL_FROM', None)
        
        if not from_email:
            # Fall back to Django's default
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        
        return from_email
    
    def _render_email_template(self, template_name: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Render email template.
        
        Args:
            template_name: Template name (without _subject.txt, _body.txt suffixes)
            context: Template context
            
        Returns:
            Rendered HTML content, or None if template doesn't exist
        """
        try:
            # Look for HTML template
            html_template = f'django_4eyes/notifications/{template_name}.html'
            return render_to_string(html_template, context)
        except Exception:
            # Template doesn't exist, use default
            return None
    
    def _send_html_email(
        self,
        recipient: User,
        subject: str,
        html_content: str,
        text_content: str,
        from_email: str
    ) -> bool:
        """
        Send HTML email.
        
        Args:
            recipient: User recipient
            subject: Email subject
            html_content: HTML body
            text_content: Plain text body
            from_email: Sender email address
            
        Returns:
            True if sent successfully
        """
        try:
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[recipient.email]
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=False)
            
            logger.info(f"Email sent to {recipient.email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send HTML email: {e}", exc_info=True)
            return False
    
    def _send_plain_email(
        self,
        recipient: User,
        subject: str,
        message: str,
        from_email: str
    ) -> bool:
        """
        Send plain text email.
        
        Args:
            recipient: User recipient
            subject: Email subject
            message: Email body
            from_email: Sender email address
            
        Returns:
            True if sent successfully
        """
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=[recipient.email],
                fail_silently=False
            )
            
            logger.info(f"Plain email sent to {recipient.email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send plain email: {e}", exc_info=True)
            return False
    
    def can_send(self, recipient: User, **kwargs) -> bool:
        """
        Check if email can be sent to this user.
        
        Args:
            recipient: User to check
            **kwargs: Additional context
            
        Returns:
            True if email can be sent
        """
        # Check if user has email
        if not recipient.email:
            return False
        
        # Check if user is active
        if not recipient.is_active:
            return False
        
        # Check if email notifications are enabled for this user
        # (could be overridden by user preferences)
        if hasattr(recipient, 'email_notifications_enabled'):
            if not recipient.email_notifications_enabled:
                return False
        
        return True