"""
Test settings for django-4eyes.
"""

SECRET_KEY = 'test-secret-key-not-for-production'

DEBUG = True

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django_4eyes',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

USE_TZ = True

APPROVAL_ALLOW_SUPERUSER_OVERRIDE = True