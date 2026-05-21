from django.urls import path

from .consumers import BibliotecaUpdatesConsumer


websocket_urlpatterns = [
    path('ws/biblioteca/', BibliotecaUpdatesConsumer.as_asgi()),
]
