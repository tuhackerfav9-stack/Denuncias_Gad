from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from db.models import Denuncias, Ciudadanos, TiposDenuncia, DenunciaFirmas, DenunciaEvidencias

def get_claim(request, key: str, default=None):
    token = getattr(request, "auth", None)
    if token is None:
        return default
    try:
        return token.get(key, default)
    except Exception:
        return default


class DenunciaDetalleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, denuncia_id):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")

        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        #  Solo deja ver denuncias del mismo ciudadano
        try:
            d = Denuncias.objects.select_related("tipo_denuncia").get(id=denuncia_id, ciudadano_id=uid)
        except Denuncias.DoesNotExist:
            return Response({"detail": "Denuncia no existe"}, status=404)

        # ciudadano (por tu modelo: Ciudadanos.usuario_id = uid)
        ciudadano = Ciudadanos.objects.filter(usuario_id=uid).first()

        # firma (1 a 1)
        firma = DenunciaFirmas.objects.filter(denuncia_id=d.id).first()

        # evidencias (lista)
        evids_qs = DenunciaEvidencias.objects.filter(denuncia_id=d.id).order_by("created_at")
        evidencias = []
        for ev in evids_qs:
            evidencias.append({
                "tipo": str(ev.tipo),
                "url_archivo": ev.url_archivo,
                "nombre_archivo": ev.nombre_archivo,
                "created_at": ev.created_at,
            })

        return Response({
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
                "nombre": getattr(d.tipo_denuncia, "nombre", None)
            },

            "ciudadano": {
                "nombres": getattr(ciudadano, "nombres", None),
                "apellidos": getattr(ciudadano, "apellidos", None),
                "cedula": getattr(ciudadano, "cedula", None),
                "correo": getattr(getattr(ciudadano, "usuario", None), "correo", None),
            },

            "firma": {
                "firma_url": getattr(firma, "firma_url", None),
                "firma_base64": getattr(firma, "firma_base64", None),
            },

            "evidencias": evidencias,
        }, status=200)
