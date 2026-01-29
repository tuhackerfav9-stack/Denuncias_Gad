import uuid
from django.conf import settings
from django.utils import timezone
from django.core.files.storage import default_storage

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser

from db.models import DenunciaBorradores

# mismo helper que ya usas
def get_claim(request, key: str, default=None):
    token = getattr(request, "auth", None)
    if token is None:
        return default
    try:
        return token.get(key, default)
    except Exception:
        return default


def _build_abs(request, relative_url: str):
    # relative_url ejemplo: /media/xxx.png
    return request.build_absolute_uri(relative_url)


class BorradorSubirEvidenciaView(APIView):
    """
    POST /api/denuncias/borradores/<id>/evidencias/
    multipart:
      - archivo: File (required)
      - tipo: "foto" | "video" (optional)
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, borrador_id):
        uid = get_claim(request, "uid")
        tipo_user = get_claim(request, "tipo")
        if not uid or tipo_user != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        try:
            b = DenunciaBorradores.objects.get(id=borrador_id, ciudadano_id=uid)
        except DenunciaBorradores.DoesNotExist:
            return Response({"detail": "Borrador no existe"}, status=404)

        archivo = request.FILES.get("archivo")
        if not archivo:
            return Response({"detail": "Falta archivo"}, status=400)

        tipo = (request.data.get("tipo") or "").strip().lower()
        if tipo not in ("foto", "video"):
            # intenta inferir por content-type
            ct = (getattr(archivo, "content_type", "") or "").lower()
            tipo = "video" if ct.startswith("video/") else "foto"

        # Guardar en MEDIA
        folder = f"denuncias/borradores/{borrador_id}/"
        safe_name = f"{uuid.uuid4()}_{archivo.name}"
        path = default_storage.save(folder + safe_name, archivo)

        url = settings.MEDIA_URL + path  # relativa
        url_abs = _build_abs(request, url)

        data = b.datos_json or {}
        evids = data.get("evidencias") or []
        evids.append({
            "tipo": tipo,
            "url_archivo": url_abs,
            "nombre_archivo": archivo.name,
            "subido_en": timezone.now().isoformat(),
        })
        data["evidencias"] = evids

        b.datos_json = data
        b.updated_at = timezone.now()
        b.save(update_fields=["datos_json", "updated_at"])

        return Response(
            {
                "detail": "Evidencia subida",
                "url_archivo": url_abs,
                "tipo": tipo,
                "total": len(evids),
            },
            status=201
        )


class BorradorSubirFirmaView(APIView):
    """
    POST /api/denuncias/borradores/<id>/firma/
    multipart:
      - firma: File (PNG/JPG)  (required)
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, borrador_id):
        uid = get_claim(request, "uid")
        tipo_user = get_claim(request, "tipo")
        if not uid or tipo_user != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        try:
            b = DenunciaBorradores.objects.get(id=borrador_id, ciudadano_id=uid)
        except DenunciaBorradores.DoesNotExist:
            return Response({"detail": "Borrador no existe"}, status=404)

        firma = request.FILES.get("firma")
        if not firma:
            return Response({"detail": "Falta firma"}, status=400)

        folder = f"denuncias/borradores/{borrador_id}/"
        safe_name = f"firma_{uuid.uuid4()}.png"
        path = default_storage.save(folder + safe_name, firma)

        url = settings.MEDIA_URL + path
        url_abs = _build_abs(request, url)

        data = b.datos_json or {}
        data["firma_url"] = url_abs

        b.datos_json = data
        b.updated_at = timezone.now()
        b.save(update_fields=["datos_json", "updated_at"])

        return Response(
            {"detail": "Firma subida", "firma_url": url_abs},
            status=201
        )
