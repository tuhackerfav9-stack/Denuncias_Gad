# denuncias_api/views_archivos.py
from django.http import HttpResponse

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from db.models import BorradorArchivo


def get_claim(request, key: str, default=None):
    token = getattr(request, "auth", None)
    if token is None:
        return default
    try:
        return token.get(key, default)
    except Exception:
        return default


class BorradorArchivoVerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, archivo_id):
        uid = get_claim(request, "uid")
        tipo_user = get_claim(request, "tipo")
        if not uid or tipo_user != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        try:
            obj = BorradorArchivo.objects.select_related("borrador").get(id=archivo_id)
        except BorradorArchivo.DoesNotExist:
            return Response({"detail": "Archivo no existe"}, status=404)

        if str(obj.borrador.ciudadano_id) != str(uid):
            return Response({"detail": "No autorizado"}, status=403)

        resp = HttpResponse(bytes(obj.data), content_type=obj.content_type or "application/octet-stream")
        if obj.filename:
            resp["Content-Disposition"] = f'inline; filename="{obj.filename}"'
        return resp

