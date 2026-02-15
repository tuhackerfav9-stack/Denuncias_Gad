from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import User, Group
from django.db import transaction
from django.utils import timezone

from db.models import Usuarios, Funcionarios, Departamentos, DenunciaRespuestas, DenunciaHistorial
from web.models import FuncionarioWebUser


def _get_departamento(dep_id: Optional[int]) -> Optional[Departamentos]:
    if dep_id:
        dep = Departamentos.objects.filter(id=dep_id).first()
        if dep:
            return dep

    default_id = getattr(settings, "DEFAULT_DEPARTAMENTO_ID", None)
    if default_id:
        dep = Departamentos.objects.filter(id=default_id).first()
        if dep:
            return dep

    return Departamentos.objects.filter(activo=True).order_by("id").first()


@dataclass
class UnifiedUserResult:
    web_user: User
    usuario_uuid: Usuarios
    funcionario: Funcionarios
    link: FuncionarioWebUser


# ------------------------------------------------------------
#  REGLA: Se puede hard delete?
# ------------------------------------------------------------
def can_hard_delete_user(user: User) -> bool:
    link = FuncionarioWebUser.objects.select_related("funcionario").filter(web_user=user).first()
    if not link:
        # no está ligado a funcionario -> no hay trazabilidad, se puede borrar
        return True

    func = link.funcionario

    # tiene respuestas?
    if DenunciaRespuestas.objects.filter(funcionario=func).exists():
        return False

    # tiene cambios de estado?
    if DenunciaHistorial.objects.filter(cambiado_por_funcionario=func).exists():
        return False

    return True


# ------------------------------------------------------------
#  CREATE / UPDATE: asegurar que existan las 4 tablas
# ------------------------------------------------------------
@transaction.atomic
def upsert_unified_user(
    *,
    web_user: User | None,
    username: str,
    email: str,
    first_name: str,
    last_name: str,
    password: str | None,
    is_superuser: bool,
    group: Group | None,
    departamento_id: int | None,
    cedula: str,
    telefono: str | None,
    cargo: str | None,
    activo: bool,
) -> UnifiedUserResult:
    """
    - Crea o actualiza auth_user
    - Crea o actualiza Usuarios (UUID)
    - Crea o actualiza Funcionarios (UUID -> Usuarios)
    - Asegura FuncionarioWebUser (puente)
    - Sincroniza nombre/apellido/correo/activo en todas
    """
    now = timezone.now()
    creating = web_user is None

    if creating:
        web_user = User(username=username)
        web_user.date_joined = now

    # -------- auth_user --------
    web_user.username = username
    web_user.email = email
    web_user.first_name = first_name
    web_user.last_name = last_name
    web_user.is_staff = True          # regla: todo “usuario web” aquí es funcionario web
    web_user.is_superuser = is_superuser
    web_user.is_active = activo

    if password:
        web_user.set_password(password)

    web_user.save()

    # Grupo: tu regla de 1 solo grupo por funcionario
    if group:
        web_user.groups.clear()
        web_user.groups.add(group)

    # -------- Usuarios (UUID) --------
    usuario_uuid, created_u = Usuarios.objects.get_or_create(
        correo=email,
        defaults={
            "tipo": "funcionario",
            "password_hash": "django_auth",
            "activo": activo,
            "correo_verificado": True,
            "created_at": now,
            "updated_at": now,
        }
    )
    # si ya existía, sincroniza
    changed_u = False
    if getattr(usuario_uuid, "activo", None) != activo:
        usuario_uuid.activo = activo
        changed_u = True
    if getattr(usuario_uuid, "correo", "") != email:
        usuario_uuid.correo = email
        changed_u = True
    if hasattr(usuario_uuid, "updated_at") and changed_u:
        usuario_uuid.updated_at = now
    if changed_u:
        usuario_uuid.save()

    # -------- Funcionarios (UUID -> Usuarios) --------
    dep = _get_departamento(departamento_id)

    funcionario, created_f = Funcionarios.objects.get_or_create(
        usuario=usuario_uuid,
        defaults={
            "cedula": cedula,
            "nombres": first_name or username,
            "apellidos": last_name or "",
            "telefono": telefono,
            "departamento": dep,
            "cargo": cargo or "OPERADOR",
            "activo": activo,
            "created_at": now,
            "updated_at": now,
        }
    )

    # sincroniza campos compartidos (tu idea)
    changed_f = False

    new_nombres = first_name or username
    new_apellidos = last_name or ""

    if (funcionario.nombres or "") != (new_nombres or ""):
        funcionario.nombres = new_nombres
        changed_f = True

    if (funcionario.apellidos or "") != (new_apellidos or ""):
        funcionario.apellidos = new_apellidos
        changed_f = True

    if hasattr(funcionario, "cedula") and (funcionario.cedula or "") != (cedula or ""):
        funcionario.cedula = cedula
        changed_f = True

    if hasattr(funcionario, "telefono") and (funcionario.telefono or "") != (telefono or ""):
        funcionario.telefono = telefono
        changed_f = True

    if hasattr(funcionario, "cargo") and (funcionario.cargo or "") != (cargo or ""):
        funcionario.cargo = cargo
        changed_f = True

    if dep and getattr(funcionario, "departamento_id", None) != dep.id:
        funcionario.departamento = dep
        changed_f = True

    if getattr(funcionario, "activo", None) != activo:
        funcionario.activo = activo
        changed_f = True

    if changed_f:
        if hasattr(funcionario, "updated_at"):
            funcionario.updated_at = now
        funcionario.save()

    # -------- puente --------
    link, _ = FuncionarioWebUser.objects.get_or_create(funcionario=funcionario, web_user=web_user)

    return UnifiedUserResult(
        web_user=web_user,
        usuario_uuid=usuario_uuid,
        funcionario=funcionario,
        link=link,
    )


# ------------------------------------------------------------
#  SOFT DISABLE (una sola implementación)
# ------------------------------------------------------------
@transaction.atomic
def soft_disable_unified_user(user: User):
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


# ------------------------------------------------------------
#  HARD DELETE seguro: limpia encadenado
# ------------------------------------------------------------
@transaction.atomic
def hard_delete_unified_user(user: User):
    """
    Borra:
    - puente
    - usuarios uuid (y por cascada/relación cae funcionario si tu DB lo hace)
    - auth_user
    """
    link = FuncionarioWebUser.objects.select_related("funcionario").filter(web_user=user).first()
    if link:
        func = link.funcionario
        usuario_uuid = getattr(func, "usuario", None)

        link.delete()
        # si quieres borrar dominio:
        if usuario_uuid:
            usuario_uuid.delete()

    user.delete()
