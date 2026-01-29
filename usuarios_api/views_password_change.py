# usuarios_api/views_password_change.py
from django.utils import timezone
from django.contrib.auth.hashers import check_password, make_password

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


from db.models import Usuarios


def get_claim(request, key: str, default=None):
    token = getattr(request, "auth", None)
    if token is None:
        return default
    try:
        return token.get(key, default)
    except Exception:
        return default


class PasswordChangeView(APIView):
    """
    POST /api/auth/password/change/
    Body:
      - password_actual
      - password_nueva
      - password_confirmar
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")

        # Solo ciudadano (como pediste)
        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        p_actual = (request.data.get("password_actual") or "").strip()
        p_nueva = (request.data.get("password_nueva") or "").strip()
        p_conf = (request.data.get("password_confirmar") or "").strip()

        if not p_actual or not p_nueva or not p_conf:
            return Response({"detail": "Todos los campos son obligatorios"}, status=400)

        if len(p_nueva) < 6:
            return Response({"detail": "La nueva contraseña debe tener mínimo 6 caracteres"}, status=400)

        if p_nueva != p_conf:
            return Response({"detail": "La confirmación no coincide"}, status=400)

        try:
            u = Usuarios.objects.get(id=uid)
        except Usuarios.DoesNotExist:
            return Response({"detail": "Usuario no existe"}, status=404)

        # Verifica password actual (usa tu hash Django)
        try:
            ok = check_password(p_actual, u.password_hash)
        except Exception:
            return Response({"detail": "Error validando contraseña actual"}, status=400)

        if not ok:
            return Response({"detail": "Contraseña actual incorrecta"}, status=400)

        # Evita reusar misma contraseña (opcional pero recomendado)
        if check_password(p_nueva, u.password_hash):
            return Response({"detail": "La nueva contraseña no puede ser igual a la actual"}, status=400)

        # Actualiza
        u.password_hash = make_password(p_nueva)
        u.updated_at = timezone.now()
        u.save(update_fields=["password_hash", "updated_at"])

        return Response({"detail": "Contraseña actualizada  "}, status=200)
