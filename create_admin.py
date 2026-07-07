"""Create the initial superuser from environment variables (no hardcoded secrets).

Usage:
    ADMIN_EMAIL=you@example.sa ADMIN_PASSWORD='<strong>' python create_admin.py

Refuses to run if either variable is missing. Idempotent: skips if the user exists.
"""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cybertrust_ksa.settings')
django.setup()

from core.models import User
from core.admin_bootstrap import create_superuser_from_env, AdminCredentialsMissing

try:
    created, email = create_superuser_from_env(os.environ, User)
except AdminCredentialsMissing as exc:
    sys.exit(f'ERROR: {exc}')

print(f'Superuser {email} created successfully.' if created
      else f'Superuser {email} already exists.')
