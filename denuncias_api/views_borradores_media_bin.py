# denuncias_api/views_borradores_media_bin.py
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser

from db.models import DenunciaBorradores, BorradorArchivo


def get_claim(request, key: str, default=None):
    token = getattr(request, "auth", None)
    if token is None:
        return default
    try:
        return token.get(key, default)
    except Exception:
        return default


MAX_FOTO   = 5 * 1024 * 1024
MAX_AUDIO  = 50 * 1024 * 1024
MAX_VIDEO  = 50 * 1024 * 1024
MAX_FIRMA  = 50 * 1024 * 1024
MAX_CEDULA = 50 * 1024 * 1024

LIMITES = {
    "foto": MAX_FOTO,
    "audio": MAX_AUDIO,
    "video": MAX_VIDEO,
    "firma": MAX_FIRMA,
    "cedula": MAX_CEDULA,
}


class BorradorSubirEvidenciaBinView(APIView):
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
        if tipo not in ("foto", "video", "audio"):
            ct = (getattr(archivo, "content_type", "") or "").lower()
            if ct.startswith("video/"):
                tipo = "video"
            elif ct.startswith("audio/"):
                tipo = "audio"
            else:
                tipo = "foto"

        size = int(getattr(archivo, "size", 0) or 0)
        limite = LIMITES.get(tipo, MAX_FOTO)
        if size > limite:
            return Response(
                {"detail": f"Archivo demasiado grande. Máximo {int(limite/1024/1024)}MB para {tipo}."},
                status=413
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

        data = b.datos_json or {}
        evids = data.get("evidencias") or []
        evids.append({
            "archivo_id": str(obj.id),
            "tipo": tipo,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(data_bytes),
            "subido_en": timezone.now().isoformat(),
        })
        data["evidencias"] = evids

        b.datos_json = data
        b.updated_at = timezone.now()
        b.save(update_fields=["datos_json", "updated_at"])

        return Response(
            {"detail": "Evidencia subida", "archivo_id": str(obj.id), "tipo": tipo, "total": len(evids)},
            status=201
        )


class BorradorSubirFirmaBinView(APIView):
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

        size = int(getattr(firma, "size", 0) or 0)
        if size > MAX_FIRMA:
            return Response({"detail": "Firma demasiado grande. Máximo 2MB."}, status=413)

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

        data = b.datos_json or {}
        data["firma_archivo_id"] = str(obj.id)

        b.datos_json = data
        b.updated_at = timezone.now()
        b.save(update_fields=["datos_json", "updated_at"])

        return Response({"detail": "Firma subida", "archivo_id": str(obj.id)}, status=201)
