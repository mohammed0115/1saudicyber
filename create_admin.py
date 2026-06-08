import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cybertrust_ksa.settings')
django.setup()

from core.models import User

if not User.objects.filter(email='admin@cybertrust.sa').exists():
    User.objects.create_superuser(
        email='admin@cybertrust.sa',
        password='CyberTrust2024',
        first_name='Admin',
        last_name='CyberTrust'
    )
    print("Superuser created successfully.")
else:
    print("Superuser already exists.")
