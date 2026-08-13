import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_user_email_verified_user_mfa_enabled_user_mfa_secret_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='FrameworkDecision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('answers', models.JSONField(default=dict)),
                ('recommended_framework_codes', models.JSONField(default=list)),
                ('rationale', models.JSONField(default=dict)),
                ('rules_version', models.CharField(default='2026.08', max_length=32)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='framework_decisions', to='core.company')),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='framework_decisions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'framework_decisions',
                'ordering': ['-created_at'],
            },
        ),
    ]
