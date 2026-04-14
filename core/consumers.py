import json
from channels.generic.websocket import AsyncWebsocketConsumer

class OlympiadConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = 'olympiads'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # Receive message from group
    async def olympiad_update(self, event):
        await self.send(text_data=json.dumps(event['data']))


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or user.is_anonymous:
            await self.close()
            return

        self.group_name = f'user_{user.id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # Receive message from group
    async def notification_send(self, event):
        await self.send(text_data=json.dumps(event['data']))
