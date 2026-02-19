# denuncias_api/views_borradores_media_bin.py

from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status

from db.models import DenunciaBorradores, BorradorArchivo
from .utils import get_claim


# =========================
# Límites (ajusta si quieres)
# =========================
MAX_FOTO   = 5 * 1024 * 1024     # 5MB
MAX_AUDIO  = 50 * 1024 * 1024    # 50MB
MAX_VIDEO  = 50 * 1024 * 1024    # 50MB
MAX_FIRMA  = 50 * 1024 * 1024    # 50MB (recomendado bajar a 2-5MB)
MAX_CEDULA = 50 * 1024 * 1024    # 50MB

LIMITES = {
    "foto": MAX_FOTO,
    "audio": MAX_AUDIO,
    "video": MAX_VIDEO,
    "firma": MAX_FIRMA,
    "cedula": MAX_CEDULA,
}

TIPOS_EVIDENCIA = ("foto", "video", "audio", "cedula")


def _mb(n_bytes: int) -> int:
    return max(1, int(n_bytes / 1024 / 1024))


def _solo_ciudadano(request):
    uid = get_claim(request, "uid")
    tipo_user = get_claim(request, "tipo")
    if not uid or tipo_user != "ciudadano":
        return None, Response({"detail": "Solo ciudadanos"}, status=status.HTTP_403_FORBIDDEN)
    return uid, None


def _get_borrador_o_404(borrador_id, uid):
    try:
        return DenunciaBorradores.objects.get(id=borrador_id, ciudadano_id=uid), None
    except DenunciaBorradores.DoesNotExist:
        return None, Response({"detail": "Borrador no existe"}, status=status.HTTP_404_NOT_FOUND)


def _inferir_tipo(archivo, tipo_enviado: str | None):
    tipo = (tipo_enviado or "").strip().lower()
    if tipo in TIPOS_EVIDENCIA:
        return tipo

    ct = (getattr(archivo, "content_type", "") or "").lower()
    if ct.startswith("video/"):
        return "video"
    if ct.startswith("audio/"):
        return "audio"

    # PDF u otros docs: si quieres tratarlos como cédula
    if ct in ("application/pdf",):
        return "cedula"

    return "foto"


class BorradorSubirEvidenciaBinView(APIView):
    """
    POST /api/denuncias/borradores/<id>/evidencias/   (si en urls apuntas aquí)
    multipart:
      - archivo: File (required)
      - tipo: foto|video|audio|cedula (optional)
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, borrador_id):
        uid, err = _solo_ciudadano(request)
        if err:
            return err

        b, err = _get_borrador_o_404(borrador_id, uid)
        if err:
            return err

        archivo = request.FILES.get("archivo")
        if not archivo:
            return Response({"detail": "Falta archivo"}, status=status.HTTP_400_BAD_REQUEST)

        tipo = _inferir_tipo(archivo, request.data.get("tipo"))

        size = int(getattr(archivo, "size", 0) or 0)
        limite = LIMITES.get(tipo, MAX_FOTO)
        if size > limite:
            return Response(
                {"detail": f"Archivo demasiado grande. Máximo {_mb(limite)}MB para {tipo}."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            )

        content_type = (getattr(archivo, "content_type", None) or "application/octet-stream")
        filename = getattr(archivo, "name", "archivo")

        data_bytes = archivo.read()

        obj = BorradorArchivo.objects.create(
            borrador=b,
            tipo=tipo,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data_bytes),
            data=data_bytes,
        )

        # URL protegida para que Flutter la use (Image.network / Video / etc.)
        url_abs = request.build_absolute_uri(f"/api/denuncias/borradores/archivos/{obj.id}/")

        data = b.datos_json or {}
        evids = data.get("evidencias") or []

        evids.append({
            "archivo_id": str(obj.id),
            "tipo": tipo,
            "url_archivo": url_abs,       # ✅ clave para Flutter
            "nombre_archivo": filename,   # ✅ consistente con tu detalle
            "content_type": content_type,
            "size_bytes": len(data_bytes),
            "subido_en": timezone.now().isoformat(),
        })

        data["evidencias"] = evids
        b.datos_json = data
        b.updated_at = timezone.now()
        b.save(update_fields=["datos_json", "updated_at"])

        return Response(
            {
                "detail": "Evidencia subida",
                "archivo_id": str(obj.id),
                "tipo": tipo,
                "url_archivo": url_abs,
                "nombre_archivo": filename,
                "total": len(evids),
            },
            status=status.HTTP_201_CREATED
        )


class BorradorSubirFirmaBinView(APIView):
    """
    POST /api/denuncias/borradores/<id>/firma/   (si en urls apuntas aquí)
    multipart:
      - firma: File (required)
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, borrador_id):
        uid, err = _solo_ciudadano(request)
        if err:
            return err

        b, err = _get_borrador_o_404(borrador_id, uid)
        if err:
            return err

        firma = request.FILES.get("firma")
        if not firma:
            return Response({"detail": "Falta firma"}, status=status.HTTP_400_BAD_REQUEST)

        size = int(getattr(firma, "size", 0) or 0)
        if size > MAX_FIRMA:
            return Response(
                {"detail": f"Firma demasiado grande. Máximo {_mb(MAX_FIRMA)}MB."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            )

        content_type = (getattr(firma, "content_type", None) or "image/png")
        filename = getattr(firma, "name", "firma.png")
        data_bytes = firma.read()

        obj = BorradorArchivo.objects.create(
            borrador=b,
            tipo="firma",
            filename=filename,
            content_type=content_type,
            size_bytes=len(data_bytes),
            data=data_bytes,
        )

        url_abs = request.build_absolute_uri(f"/api/denuncias/borradores/archivos/{obj.id}/")

        data = b.datos_json or {}
        data["firma_archivo_id"] = str(obj.id)
        data["firma_url"] = url_abs  # ✅ Flutter: Image.network

        b.datos_json = data
        b.updated_at = timezone.now()
        b.save(update_fields=["datos_json", "updated_at"])

        return Response(
            {"detail": "Firma subida", "archivo_id": str(obj.id), "firma_url": url_abs},
            status=status.HTTP_201_CREATED
        )
