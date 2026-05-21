# Generated manually for Django 6.0.3

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_merge_20260422_1804'),
    ]

    operations = [
        migrations.CreateModel(
            name='SMSSentHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('template_id', models.CharField(db_index=True, max_length=100)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sms_history', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'История отправки СМС',
                'verbose_name_plural': 'История отправки СМС',
                'unique_together': {('user', 'template_id')},
            },
        ),
    ]
