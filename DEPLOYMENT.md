# django-4eyes Deployment Guide

## Package Structure

The django-4eyes package is now ready for PyPI deployment. Here's what's included:

```
django-4eyes/
├── django_4eyes/              # Main package
│   ├── __init__.py            # Package initialization
│   ├── apps.py                # Django app configuration
│   ├── engine.py              # Approval workflow engine
│   ├── signals.py             # Signal handlers
│   ├── models/                # Models package
│   │   ├── __init__.py
│   │   ├── base.py            # FourEyeModel, ApprovalMixin
│   │   ├── approval.py        # ApprovalTemplate, ApprovalStep, ApprovalState
│   │   └── notification.py    # Notification model
│   └── migrations/            # Database migrations
│       ├── __init__.py
│       └── 0001_initial.py
├── example/                   # Example Django project
│   ├── manage.py
│   ├── example/               # Project settings
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   └── example_app/           # Example app
│       ├── __init__.py
│       ├── models.py
│       └── admin.py
├── tests/                     # Test suite
│   ├── __init__.py
│   ├── settings.py
│   └── test_models.py
├── README.md                  # Main documentation
├── LICENSE                    # MIT License
├── setup.py                   # Package setup
└── pyproject.toml            # Modern Python project metadata
```

## Testing

All tests pass successfully:

```bash
# Run tests
DJANGO_SETTINGS_MODULE=tests.settings python -m django test tests.test_models --verbosity=2
```

## Building the Package

The package has been built successfully:

```bash
# Install build tool
pip install build

# Build source distribution and wheel
python -m build

# Output:
# dist/django_4eyes-1.0.0.tar.gz
# dist/django_4eyes-1.0.0-py3-none-any.whl
```

## Publishing to PyPI

### 1. Install twine

```bash
pip install twine
```

### 2. Upload to TestPyPI (for testing)

```bash
# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ django-4eyes
```

### 3. Upload to PyPI (production)

```bash
# Upload to PyPI
twine upload dist/*

# Install from PyPI
pip install django-4eyes
```

## Pre-deployment Checklist

- [x] All tests pass
- [x] Package builds successfully
- [x] README is comprehensive
- [x] LICENSE is included
- [x] setup.py and pyproject.toml are configured
- [x] Migrations are created
- [x] Example project demonstrates usage
- [ ] PyPI account created
- [ ] Package name verified as available
- [ ] Version number is correct (1.0.0)
- [ ] Author information updated

## Updating Author Information

Before publishing, update these files with your information:

1. **setup.py**:
   - `AUTHOR`
   - `AUTHOR_EMAIL`
   - `URL`

2. **pyproject.toml**:
   - `authors`
   - `maintainers`
   - URLs

3. **django_4eyes/__init__.py**:
   - `__author__`

4. **LICENSE**:
   - Copyright year and name

5. **README.md**:
   - GitHub URL
   - Support links

## Post-deployment

After publishing to PyPI:

1. **Create a GitHub repository** and push the code
2. **Set up documentation** on ReadTheDocs (optional)
3. **Add CI/CD** with GitHub Actions (optional)
4. **Announce the release** on Django forums, Reddit, etc.

## Version Updates

To release a new version:

1. Update version in:
   - `django_4eyes/__init__.py`
   - `setup.py`
   - `pyproject.toml`

2. Update CHANGELOG.md

3. Rebuild:
   ```bash
   python -m build
   ```

4. Upload:
   ```bash
   twine upload dist/*
   ```

## Support

For issues or questions about deployment:
- PyPI Help: https://pypi.org/help/
- Twine Docs: https://twine.readthedocs.io/
- Python Packaging: https://packaging.python.org/