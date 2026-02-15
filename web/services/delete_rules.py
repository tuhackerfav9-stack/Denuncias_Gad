from django.contrib.auth.models import User
from django.db.models import Exists, OuterRef

from db.models import (
    DenunciaRespuestas,
    DenunciaHistorial,
    Funcionarios,
    Usuarios,  # <- tu tabla puente (funcionario_web_user)
)
from web.models import FuncionarioWebUser

# -------------------------------
# Obtener funcionarios ligados a un auth_user
# -------------------------------
def get_funcionarios_de_webuser(user: User):
    """
    Devuelve queryset de Funcionarios asociados a este auth_user
    usando la tabla puente funcionario_web_user.
    """
    funcionario_ids = FuncionarioWebUser.objects.filter(
        web_user_id=user.id
    ).values_list("funcionario_id", flat=True)

    return Funcionarios.objects.filter(usuario__in=funcionario_ids)  # to_field='usuario'


# -------------------------------
# Regla: hard delete permitido?
# -------------------------------
def can_hard_delete_user(user: User) -> bool:
    """
    True si se puede eliminar definitivamente sin romper trazabilidad.
    Regla: si tiene evidencias de 'denuncias tratadas' => NO.
    'Tratadas' = tiene respuestas o cambios de estado.
    """
    funcionarios = get_funcionarios_de_webuser(user)
    if not funcionarios.exists():
        # si nunca estuvo ligado a funcionario, se puede borrar (no hay historial)
        return True

    # si ya respondió denuncias
    if DenunciaRespuestas.objects.filter(funcionario__in=funcionarios).exists():
        return False

    # si ya cambió estados (historial)
    if DenunciaHistorial.objects.filter(cambiado_por_funcionario__in=funcionarios).exists():
        return False

    return True


# -------------------------------
# Soft delete: desactivar usuario (y opcional dominio)
# -------------------------------
def soft_disable_web_user(user: User):
    """
    Soft delete seguro:
    - auth_user.is_active = False
    - Funcionarios.activo = False (si aplica)
    - Usuarios.activo = False (si aplica)
    """
    # 1) Desactivar auth_user
    if user.is_active:
        user.is_active = False
        user.save(update_fields=["is_active"])

    funcionarios = get_funcionarios_de_webuser(user)
    if funcionarios.exists():
        # 2) Desactivar funcionarios
        funcionarios.update(activo=False)

        # 3) Desactivar 'usuarios' (tabla dominio) por UUID (pk igual al funcionario.usuario)
        usuario_ids = funcionarios.values_list("usuario", flat=True)
        Usuarios.objects.filter(id__in=usuario_ids).update(activo=False)
