import json

from channels.generic.websocket import AsyncWebsocketConsumer


class BibliotecaUpdatesConsumer(AsyncWebsocketConsumer):
    group_name = 'biblioteca_updates'

    async def connect(self):
        if not self.scope.get('user') or not self.scope['user'].is_authenticated:
            await self.close()
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def biblioteca_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'biblioteca.update',
            'evento': event.get('evento', 'actualizacion'),
        }))
