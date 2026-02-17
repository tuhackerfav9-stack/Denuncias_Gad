from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import User

from db.models import Usuarios, Funcionarios, Departamentos
from web.models import FuncionarioWebUser


def get_departamento(dep_id: int | None):
    if dep_id:
        return Departamentos.objects.filter(id=dep_id).first()
    # si no me dan dep_id, NO invento uno
    return None



@transaction.atomic
def ensure_domain_for_web_user(user: User, departamento_id: int | None = None):
    """
    Si user.is_staff=True, asegura:
    - Usuarios (UUID domain)
    - Funcionarios (dep asignado)
    - FuncionarioWebUser (puente)
    """
    if not user.is_staff:
        return None
    if not user.email:
        return None

    now = timezone.now()

    u, _ = Usuarios.objects.get_or_create(
        correo=user.email,
        defaults={
            "tipo": "funcionario",
            "password_hash": "django_auth",
            "activo": True,
            "correo_verificado": True,
            "created_at": now,
            "updated_at": now,
        }
    )

    dep = get_departamento(departamento_id)

    f, created_f = Funcionarios.objects.get_or_create(
        usuario=u,
        defaults={
            "cedula": f"TMP-{user.id}",
            "nombres": user.first_name or user.username,
            "apellidos": user.last_name or "",
            "telefono": None,
            **({"departamento": dep} if dep else {}),
            "cargo": "OPERADOR",
            "activo": True,
            "created_at": now,
            "updated_at": now,
        }
    )

    # sincroniza nombres/departamento si ya existía
    changed = False
    new_nombres = user.first_name or user.username
    new_apellidos = user.last_name or ""
    if (f.nombres or "") != (new_nombres or ""):
        f.nombres = new_nombres
        changed = True
    if (f.apellidos or "") != (new_apellidos or ""):
        f.apellidos = new_apellidos
        changed = True
    if dep and getattr(f, "departamento_id", None) != dep.id:
        f.departamento = dep
        changed = True

    if changed:
        f.updated_at = now
        f.save()

    FuncionarioWebUser.objects.get_or_create(funcionario=f, web_user=user)
    return f


@transaction.atomic
def detach_domain_for_web_user(user: User):
    """
    Hard delete: limpia link y elimina Usuarios UUID (cascada baja Funcionarios)
    """
    link = FuncionarioWebUser.objects.select_related("funcionario").filter(web_user=user).first()
    if not link:
        return

    funcionario = link.funcionario
    usuario_uuid = getattr(funcionario, "usuario", None)

    link.delete()
    if usuario_uuid:
        usuario_uuid.delete()


@transaction.atomic
def soft_disable_web_user(user: User):
    """
    Soft delete: user.is_active=False + baja activo en dominio
    """
    now = timezone.now()
    if user.is_active:
        user.is_active = False
        user.save(update_fields=["is_active"])

    link = FuncionarioWebUser.objects.select_related("funcionario").filter(web_user=user).first()
    if not link:
        return

    func = link.funcionario
    if hasattr(func, "activo") and func.activo:
        func.activo = False
        if hasattr(func, "updated_at"):
            func.updated_at = now
        func.save()

    u = getattr(func, "usuario", None)
    if u and hasattr(u, "activo") and u.activo:
        u.activo = False
        if hasattr(u, "updated_at"):
            u.updated_at = now
        u.save()
