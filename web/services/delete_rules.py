from web.models import FuncionarioWebUser

# AJUSTA ESTE IMPORT al app real donde está Denuncia en tu Django
from db.models import Denuncia  # <-- cambia si tu ruta es otra


def can_hard_delete_user(user) -> bool:
    """
    True si se puede borrar definitivo (hard delete).
    Regla: si tiene denuncias tratadas/asignadas -> NO.
    """
    link = FuncionarioWebUser.objects.select_related("funcionario").filter(web_user=user).first()
    if not link:
        # si no tiene funcionario asociado, se puede borrar
        return True

    funcionario = link.funcionario

    # ✅ REGLA "tratadas": ajusta según tus estados reales
    # Opción A (recomendada): todo lo que NO sea 'pendiente' cuenta como "en proceso"
    tiene_tratadas = Denuncia.objects.filter(funcionario=funcionario).exclude(estado="pendiente").exists()

    return not tiene_tratadas
