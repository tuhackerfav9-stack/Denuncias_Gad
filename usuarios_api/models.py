from django.db import models

# Create your models here.
import uuid

class RegistroCiudadanoBorrador(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    cedula = models.CharField(max_length=15)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20, null=True, blank=True)

    correo = models.CharField(max_length=150, null=True, blank=True)
    codigo_6 = models.CharField(max_length=6, null=True, blank=True)
    codigo_expira = models.DateTimeField(null=True, blank=True)
    correo_verificado = models.BooleanField(default=False)

    fecha_nacimiento = models.DateField(null=True, blank=True)

    cedula_frontal_url = models.TextField(null=True, blank=True)
    cedula_trasera_url = models.TextField(null=True, blank=True)

    finalizado = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "registro_ciudadano_borrador"
