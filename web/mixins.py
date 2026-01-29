from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

class FuncionarioRequiredMixin(LoginRequiredMixin):
    """
    - Obliga login
    - Permite superuser siempre
    - Opcional: valida que exista un Funcionario ligado al usuario
    """
    def dispatch(self, request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        if user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        # Si tu modelo Funcionario se llama distinto, cámbialo
        # y si tu relación es user->funcionario por FK/OneToOne, ajusta:
        try:
            from .models import Funcionarios
            existe = Funcionarios.objects.filter(usuario=user).exists()
        except Exception:
            existe = True  # no bloquea si no puede validar (evita romper el proyecto)

        if not existe:
            raise PermissionDenied("No tienes un perfil de funcionario vinculado.")

        return super().dispatch(request, *args, **kwargs)
