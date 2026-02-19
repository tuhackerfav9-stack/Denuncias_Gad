# denuncias_api/views_archivos.py

from django.http import HttpResponse

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from db.models import BorradorArchivo, DenunciaArchivo
from .utils import get_claim


def _safe_filename(name: str | None) -> str | None:
    """
    Evita caracteres raros en Content-Disposition (seguridad básica).
    """
    if not name:
        return None
    return name.replace("\n", "").replace("\r", "").replace('"', "").strip()


def _file_response(obj):
    """
    Devuelve el binario en inline para que se pueda ver en navegador.
    """
    content_type = getattr(obj, "content_type", None) or "application/octet-stream"
    resp = HttpResponse(bytes(obj.data), content_type=content_type)

    filename = _safe_filename(getattr(obj, "filename", None))
    if filename:
        resp["Content-Disposition"] = f'inline; filename="{filename}"'

    # seguridad básica
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "no-store"
    return resp


class BorradorArchivoVerView(APIView):
    """
    GET /api/denuncias/borradores/archivos/<uuid:archivo_id>/
    Sirve archivos BIN asociados a un borrador (solo dueño).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, archivo_id):
        uid = get_claim(request, "uid")
        tipo_user = get_claim(request, "tipo")

        if not uid or tipo_user != "ciudadano":
            return Response(
                {"detail": "Solo ciudadanos"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            obj = BorradorArchivo.objects.select_related("borrador").get(id=archivo_id)
        except BorradorArchivo.DoesNotExist:
            return Response(
                {"detail": "Archivo no existe"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Seguridad: el archivo pertenece a un borrador del ciudadano autenticado
        if str(obj.borrador.ciudadano_id) != str(uid):
            return Response(
                {"detail": "No autorizado"},
                status=status.HTTP_403_FORBIDDEN
            )

        return _file_response(obj)


class DenunciaArchivoVerView(APIView):
    """
    GET /api/denuncias/archivos/denuncia/<uuid:archivo_id>/
    Sirve archivos BIN asociados a una denuncia (solo dueño).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, archivo_id):
        uid = get_claim(request, "uid")
        tipo_user = get_claim(request, "tipo")

        if not uid or tipo_user != "ciudadano":
            return Response(
                {"detail": "Solo ciudadanos"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            obj = DenunciaArchivo.objects.select_related("denuncia").get(id=archivo_id)
        except DenunciaArchivo.DoesNotExist:
            return Response(
                {"detail": "Archivo no existe"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Seguridad: la denuncia pertenece al ciudadano autenticado
        if str(obj.denuncia.ciudadano_id) != str(uid):
            return Response(
                {"detail": "No autorizado"},
                status=status.HTTP_403_FORBIDDEN
            )

        return _file_response(obj)
