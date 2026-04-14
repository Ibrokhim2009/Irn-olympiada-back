from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Olympiad, SubOlympiad, Notification

@receiver(post_save, sender=Olympiad)
def olympiad_status_update(sender, instance, created, **kwargs):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'olympiads',
        {
            'type': 'olympiad_update',
            'data': {
                'type': 'status_change',
                'olympiad_id': instance.id,
                'is_started': instance.is_started,
                'is_completed': instance.is_completed,
                'title': instance.title_ru
            }
        }
    )

@receiver(post_save, sender=SubOlympiad)
def sub_olympiad_status_update(sender, instance, created, **kwargs):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'olympiads',
        {
            'type': 'olympiad_update',
            'data': {
                'type': 'sub_status_change',
                'sub_id': instance.id,
                'olympiad_id': instance.olympiad.id,
                'is_started': instance.is_started,
                'is_completed': instance.is_completed,
                'title': instance.title_ru
            }
        }
    )

@receiver(post_save, sender=Notification)
def notification_created(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'user_{instance.user.id}',
            {
                'type': 'notification_send',
                'data': {
                    'id': instance.id,
                    'title_ru': instance.title_ru,
                    'title_uz': instance.title_uz,
                    'message_ru': instance.message_ru,
                    'message_uz': instance.message_uz,
                    'type': instance.type,
                    'created_at': instance.created_at.isoformat()
                }
            }
        )
