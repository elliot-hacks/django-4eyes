"""
django-4eyes - Enterprise-grade approval workflow engine for Django

A reusable Django approval workflow engine that brings enterprise-grade
four-eyes principle (maker-checker) to your Django models.
"""

__version__ = '1.0.0'
__author__ = 'Elliot Hacks <thisguyhack@gmail.com>'
__all__ = ['FourEyeModel', 'ApprovalTemplate', 'ApprovalStep', 'ApprovalState', 'Notification']

default_app_config = 'django_4eyes.apps.Django4EyesConfig'