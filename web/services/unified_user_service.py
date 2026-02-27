from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import User, Group
from django.db import transaction
from django.utils import timezone

from db.models import (
    Usuarios,
    Funcionarios,
    Departamentos,
    DenunciaRespuestas,
    DenunciaHistorial,
    Denuncias,
)
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
# HELPERS DE RELACIÓN
# ------------------------------------------------------------
def _get_link_for_user(user: User) -> Optional[FuncionarioWebUser]:
    return (
        FuncionarioWebUser.objects
        .select_related("funcionario", "funcionario__usuario", "web_user")
        .filter(web_user=user)
        .first()
    )


def _get_funcionario_for_user(user: User) -> Optional[Funcionarios]:
    link = _get_link_for_user(user)
    return link.funcionario if link and link.funcionario else None


# ------------------------------------------------------------
# REGLA: Se puede hard delete?
# ------------------------------------------------------------
def can_hard_delete_user(user: User) -> bool:
    func = _get_funcionario_for_user(user)
    if not func:
        # si no está ligado a funcionario, no hay trazabilidad
        return True

    if DenunciaRespuestas.objects.filter(funcionario=func).exists():
        return False

    if DenunciaHistorial.objects.filter(cambiado_por_funcionario=func).exists():
        return False

    return True


# ------------------------------------------------------------
# REGLA: denuncias abiertas asignadas al funcionario
# ------------------------------------------------------------
def get_open_assigned_denuncias_count(user: User) -> int:
    func = _get_funcionario_for_user(user)
    if not func:
        return 0

    return (
        Denuncias.objects
        .filter(asignado_funcionario=func)
        .exclude(estado__in=["resuelta", "rechazada"])
        .count()
    )


def get_soft_disable_block_reason(user: User) -> str | None:
    abiertas = get_open_assigned_denuncias_count(user)
    if abiertas <= 0:
        return None

    func = _get_funcionario_for_user(user)
    if not func:
        return None

    estados = (
        Denuncias.objects
        .filter(asignado_funcionario=func)
        .exclude(estado__in=["resuelta", "rechazada"])
        .values_list("estado", flat=True)
        .distinct()
    )

    estados_txt = ", ".join(sorted(estados)) if estados else "sin estado identificado"

    return (
        f"No se puede desactivar porque el funcionario tiene {abiertas} "
        f"denuncia(s) aún no finalizada(s) asignada(s). "
        f"Estados detectados: {estados_txt}. "
        f"Primero finaliza o reasigna esas denuncias."
    )


def can_soft_disable_user(user: User) -> bool:
    return get_soft_disable_block_reason(user) is None


# ------------------------------------------------------------
# CREATE / UPDATE: asegurar que existan las 4 tablas
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

    # =========================================================
    # auth_user
    # =========================================================
    if creating:
        web_user = User(username=username)
        web_user.date_joined = now

    # Validación: si se intenta desactivar un usuario ya activo
    if web_user.pk and web_user.is_active and not activo:
        block_reason = get_soft_disable_block_reason(web_user)
        if block_reason:
            raise ValueError(block_reason)

    web_user.username = username
    web_user.email = email
    web_user.first_name = first_name
    web_user.last_name = last_name
    web_user.is_staff = True
    web_user.is_superuser = is_superuser
    web_user.is_active = activo

    if password:
        web_user.set_password(password)

    web_user.save()

    # Regla: un solo grupo
    web_user.groups.clear()
    if group:
        web_user.groups.add(group)

    # =========================================================
    # buscar vínculo actual si existe
    # =========================================================
    link = _get_link_for_user(web_user)
    usuario_uuid = None
    funcionario = None

    if link and getattr(link, "funcionario", None):
        funcionario = link.funcionario
        usuario_uuid = getattr(funcionario, "usuario", None)

    # =========================================================
    # Usuarios (UUID)
    # =========================================================
    if not usuario_uuid:
        usuario_uuid = Usuarios.objects.filter(correo=email).first()

    if not usuario_uuid:
        usuario_uuid = Usuarios.objects.create(
            tipo="funcionario",
            correo=email,
            password_hash="django_auth",
            activo=activo,
            correo_verificado=True,
            created_at=now,
            updated_at=now,
        )
    else:
        changed_u = False

        if getattr(usuario_uuid, "correo", "") != email:
            usuario_uuid.correo = email
            changed_u = True

        if getattr(usuario_uuid, "activo", None) != activo:
            usuario_uuid.activo = activo
            changed_u = True

        if hasattr(usuario_uuid, "updated_at") and changed_u:
            usuario_uuid.updated_at = now

        if changed_u:
            usuario_uuid.save()

    # =========================================================
    # Funcionarios
    # =========================================================
    dep = _get_departamento(departamento_id)

    if not funcionario:
        funcionario = Funcionarios.objects.filter(usuario=usuario_uuid).first()

    if not funcionario:
        funcionario = Funcionarios.objects.create(
            usuario=usuario_uuid,
            cedula=cedula,
            nombres=first_name or username,
            apellidos=last_name or "",
            telefono=telefono,
            departamento=dep,
            cargo=cargo or "OPERADOR",
            activo=activo,
            created_at=now,
            updated_at=now,
        )
    else:
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

        if hasattr(funcionario, "usuario_id") and funcionario.usuario_id != usuario_uuid.id:
            funcionario.usuario = usuario_uuid
            changed_f = True

        if changed_f:
            if hasattr(funcionario, "updated_at"):
                funcionario.updated_at = now
            funcionario.save()

    # =========================================================
    # Puente
    # =========================================================
    link, _ = FuncionarioWebUser.objects.get_or_create(
        funcionario=funcionario,
        defaults={"web_user": web_user},
    )

    if link.web_user_id != web_user.id:
        link.web_user = web_user
        link.save(update_fields=["web_user"])

    return UnifiedUserResult(
        web_user=web_user,
        usuario_uuid=usuario_uuid,
        funcionario=funcionario,
        link=link,
    )


# ------------------------------------------------------------
# SOFT DISABLE
# ------------------------------------------------------------
@transaction.atomic
def soft_disable_unified_user(user: User):
    now = timezone.now()

    block_reason = get_soft_disable_block_reason(user)
    if block_reason:
        raise ValueError(block_reason)

    if user.is_active:
        user.is_active = False
        user.save(update_fields=["is_active"])

    link = _get_link_for_user(user)
    if not link or not link.funcionario:
        return

    func = link.funcionario

    if hasattr(func, "activo") and func.activo:
        func.activo = False
        if hasattr(func, "updated_at"):
            func.updated_at = now
        func.save()

    usuario_uuid = getattr(func, "usuario", None)
    if usuario_uuid and hasattr(usuario_uuid, "activo") and usuario_uuid.activo:
        usuario_uuid.activo = False
        if hasattr(usuario_uuid, "updated_at"):
            usuario_uuid.updated_at = now
        usuario_uuid.save()


# ------------------------------------------------------------
# HARD DELETE seguro
# ------------------------------------------------------------
@transaction.atomic
def hard_delete_unified_user(user: User):
    """
    Borra:
    - puente
    - funcionario
    - usuario uuid
    - auth_user
    Solo debe llamarse si can_hard_delete_user(user) == True
    """
    link = _get_link_for_user(user)

    funcionario = None
    usuario_uuid = None

    if link:
        funcionario = link.funcionario
        usuario_uuid = getattr(funcionario, "usuario", None)

        link.delete()

    if funcionario:
        funcionario.delete()

    if usuario_uuid:
        usuario_uuid.delete()

    user.delete()