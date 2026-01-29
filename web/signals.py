from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.db import transaction
from django.conf import settings

from db.models import Usuarios, Funcionarios, Departamentos
from web.models import FuncionarioWebUser


@receiver(post_save, sender=User)
def crear_domain_user_y_funcionario(sender, instance: User, created, **kwargs):
    if not created:
        return

    # Solo usuarios web (funcionarios/admin)
    if not instance.is_staff:
        return

    # Email obligatorio para Usuarios (unique)
    if not instance.email:
        return

    with transaction.atomic():
        # 1) Crear Usuarios (UUID domain)
        u, _ = Usuarios.objects.get_or_create(
            correo=instance.email,
            defaults={
                "tipo": "funcionario",
                "password_hash": "django_auth",
                "activo": True,
                "correo_verificado": True,
            }
        )

        # 2) Departamento por defecto (por ID, más seguro que por nombre)
        dep = Departamentos.objects.filter(id=getattr(settings, "DEFAULT_DEPARTAMENTO_ID", 5)).first()

        # Si tu campo departamento NO permite null y no encuentra dep, fallback al primero activo
        if dep is None:
            dep = Departamentos.objects.filter(activo=True).order_by("id").first()

        # 3) Crear funcionario mínimo
        f, _ = Funcionarios.objects.get_or_create(
            usuario=u,
            defaults={
                "cedula": f"TMP-{instance.id}",
                "nombres": instance.first_name or instance.username,
                "apellidos": instance.last_name or "",
                "telefono": None,
                "departamento": dep,
                "cargo": "OPERADOR",
                "activo": True
            }
        )

        # 4) Puente
        FuncionarioWebUser.objects.get_or_create(
            funcionario=f,
            web_user=instance
        )
