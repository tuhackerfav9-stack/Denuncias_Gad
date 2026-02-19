# denuncias_api/views_detalle.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from db.models import Denuncias, Ciudadanos, DenunciaFirmas, DenunciaEvidencias
from .utils import get_claim


def _abs_url(request, url: str | None):
    """
    Convierte URL relativa (/api/... o /media/...) a absoluta.
    Si ya es http(s), la deja tal cual.
    """
    if not url:
        return None

    url = str(url).strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url

    if not url.startswith("/"):
        url = "/" + url

    return request.build_absolute_uri(url)


class DenunciaDetalleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, denuncia_id):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")

        if not uid or tipo != "ciudadano":
            return Response(
                {"detail": "Solo ciudadanos"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Solo deja ver denuncias del mismo ciudadano
        try:
            d = (
                Denuncias.objects
                .select_related("tipo_denuncia")
                .get(id=denuncia_id, ciudadano_id=uid)
            )
        except Denuncias.DoesNotExist:
            return Response(
                {"detail": "Denuncia no existe"},
                status=status.HTTP_404_NOT_FOUND
            )

        ciudadano = Ciudadanos.objects.filter(usuario_id=uid).first()

        # Firma (1 a 1)
        firma = DenunciaFirmas.objects.filter(denuncia_id=d.id).first()
        firma_url = _abs_url(request, getattr(firma, "firma_url", None))

        # Evidencias (lista)
        evids_qs = DenunciaEvidencias.objects.filter(denuncia_id=d.id).order_by("created_at")
        evidencias = []
        for ev in evids_qs:
            evidencias.append({
                "tipo": str(ev.tipo),
                "url_archivo": _abs_url(request, getattr(ev, "url_archivo", None)),
                "nombre_archivo": ev.nombre_archivo,
                "created_at": ev.created_at,
            })

        return Response(
            {
                "id": str(d.id),
                "estado": str(d.estado),
                "descripcion": d.descripcion,
                "referencia": d.referencia,
                "direccion_texto": d.direccion_texto,
                "latitud": float(d.latitud),
                "longitud": float(d.longitud),
                "created_at": d.created_at,

                "tipo_denuncia": {
                    "id": d.tipo_denuncia_id,
                    "nombre": getattr(d.tipo_denuncia, "nombre", None),
                },

                "ciudadano": {
                    "nombres": getattr(ciudadano, "nombres", None) if ciudadano else None,
                    "apellidos": getattr(ciudadano, "apellidos", None) if ciudadano else None,
                    "cedula": getattr(ciudadano, "cedula", None) if ciudadano else None,
                    "correo": getattr(getattr(ciudadano, "usuario", None), "correo", None) if ciudadano else None,
                },

                "firma": {
                    "firma_url": firma_url,
                    "firma_base64": getattr(firma, "firma_base64", None),
                },

                "evidencias": evidencias,
            },
            status=status.HTTP_200_OK
        )
