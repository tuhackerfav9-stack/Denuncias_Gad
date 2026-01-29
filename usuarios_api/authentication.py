from types import SimpleNamespace

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed

from db.models import Usuarios


class UsuariosJWTAuthentication(JWTAuthentication):
    """
    Autenticación JWT usando la tabla real `usuarios` (UUID),
    NO el auth_user de Django (int).
    """

    def get_user(self, validated_token):
        uid = validated_token.get("uid")  # tu claim personalizado

        if not uid:
            raise AuthenticationFailed("Token sin uid", code="token_not_valid")

        try:
            usuario = Usuarios.objects.get(id=uid)
        except Usuarios.DoesNotExist:
            raise AuthenticationFailed("Usuario no existe", code="token_not_valid")

        if not usuario.activo:
            raise AuthenticationFailed("Usuario inactivo", code="token_not_valid")

        # Creamos un "user" válido para DRF (is_authenticated=True)
        return SimpleNamespace(
            is_authenticated=True,
            id=usuario.id,
            tipo=usuario.tipo,
            correo=usuario.correo,
            usuario_db=usuario,   # por si necesitas el objeto entero
        )
