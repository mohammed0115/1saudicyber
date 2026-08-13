from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('compliance', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='evidence',
            name='processing_attempts',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='evidence',
            name='processing_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='evidence',
            name='task_id',
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
    ]
