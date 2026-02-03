from django.db import models
from db.models import Funcionarios
from django.conf import settings
from django.contrib.auth.models import User
# Create your models here.

from django.db import models
from django.contrib.auth.models import Group

class Menus(models.Model):
    nombre = models.CharField(max_length=100)
    url = models.CharField(max_length=200, blank=True, null=True)
    icono = models.CharField(max_length=100, blank=True, null=True)
    orden = models.PositiveIntegerField(default=0)
    padre = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="submenus",
        on_delete=models.CASCADE
    )

    # Roles que ven el menú
    permisos = models.ManyToManyField(
        Group,
        blank=True,
        related_name="menus_visibles"
    )

    def __str__(self):
        return self.nombre


class FuncionarioWebUser(models.Model):
    funcionario = models.OneToOneField(
        Funcionarios,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column='funcionario_id',
        to_field='usuario',
        related_name='web_link'
    )
    web_user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        db_column='web_user_id',
        related_name='funcionario_link'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'funcionario_web_user'

    def __str__(self):
        return f"{self.funcionario.nombres} {self.funcionario.apellidos} <-> {self.web_user.username}"
