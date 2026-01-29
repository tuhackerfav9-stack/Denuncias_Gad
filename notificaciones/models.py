# notificaciones/models.py
import uuid
from django.db import models

class DeviceToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario_id = models.UUIDField(db_index=True)
    fcm_token = models.TextField(unique=True)
    platform = models.CharField(max_length=20, default="android")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
