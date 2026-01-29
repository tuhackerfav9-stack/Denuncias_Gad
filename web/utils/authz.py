# web/utils/authz.py (nuevo)
from web.models import FuncionarioWebUser

def get_funcionario_from_request_user(user):
    link = (
        FuncionarioWebUser.objects
        .select_related("funcionario", "funcionario__departamento")
        .filter(web_user=user)
        .first()
    )
    return link.funcionario if link else None
