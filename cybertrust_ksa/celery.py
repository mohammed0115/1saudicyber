"""Celery application for CyberTrust KSA (async AI processing + scheduled monitoring)."""
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cybertrust_ksa.settings')

app = Celery('cybertrust_ksa')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
