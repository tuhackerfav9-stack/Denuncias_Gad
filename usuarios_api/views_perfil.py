from django.db import transaction
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from db.models import Usuarios, Ciudadanos
from .serializers_perfil import PerfilUpdateSerializer


def get_claim(request, key: str, default=None):
    token = getattr(request, "auth", None)
    if token is None:
        return default
    try:
        return token.get(key, default)
    except Exception:
        return default


class PerfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")

        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        try:
            u = Usuarios.objects.get(id=uid)
        except Usuarios.DoesNotExist:
            return Response({"detail": "Usuario no existe"}, status=404)

        c = Ciudadanos.objects.filter(usuario_id=uid).first()

        data = {
            "uid": str(uid),
            "correo": u.correo,

            #  campos reales en ciudadanos
            "nombres": c.nombres if c else "",
            "apellidos": c.apellidos if c else "",
            "telefono": c.telefono if c and c.telefono else "",
            "fecha_nacimiento": c.fecha_nacimiento if c else None,

            # opcional útil para frontend (si quieres)
            "cedula": c.cedula if c else None,
            "foto_perfil_url": c.foto_perfil_url if c else None,
        }

        return Response(data, status=200)

    def patch(self, request):
        return self._update(request, partial=True)

    def put(self, request):
        return self._update(request, partial=False)

    def _update(self, request, partial: bool):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")

        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        ser = PerfilUpdateSerializer(data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data

        try:
            u = Usuarios.objects.get(id=uid)
        except Usuarios.DoesNotExist:
            return Response({"detail": "Usuario no existe"}, status=404)

        c = Ciudadanos.objects.filter(usuario_id=uid).first()
        if not c:
            # si no existe, lo creamos
            # OJO: ciudadanos.cedula es NOT NULL y unique en tu modelo,
            # así que si tu BD exige cedula obligatoria, esto va a fallar.
            # En ese caso, NO crees el ciudadano aquí; devuelve error.
            return Response(
                {"detail": "Perfil ciudadano no existe (ciudadanos). No se puede actualizar."},
                status=400
            )

        now = timezone.now()

        with transaction.atomic():
            #  si quieres permitir cambiar correo:
            if "correo" in v:
                u.correo = v["correo"]
                u.updated_at = now
                u.save(update_fields=["correo", "updated_at"])

            #  ciudadanos reales
            update_fields = []
            if "nombres" in v:
                c.nombres = v["nombres"]
                update_fields.append("nombres")
            if "apellidos" in v:
                c.apellidos = v["apellidos"]
                update_fields.append("apellidos")
            if "telefono" in v:
                c.telefono = v["telefono"]
                update_fields.append("telefono")
            if "fecha_nacimiento" in v:
                c.fecha_nacimiento = v["fecha_nacimiento"]
                update_fields.append("fecha_nacimiento")

            if update_fields:
                c.updated_at = now
                update_fields.append("updated_at")
                c.save(update_fields=update_fields)

        return Response({"detail": "Perfil actualizado"}, status=200)
