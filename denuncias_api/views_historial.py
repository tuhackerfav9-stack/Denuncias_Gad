# denuncias_api/views_historial.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from db.models import Denuncias, DenunciaHistorial

from .utils import get_claim

class DenunciaHistorialView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, denuncia_id):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")
        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        try:
            d = Denuncias.objects.get(id=denuncia_id, ciudadano_id=uid)
        except Denuncias.DoesNotExist:
            return Response({"detail": "Denuncia no existe"}, status=404)

        qs = DenunciaHistorial.objects.filter(denuncia_id=d.id).order_by("fecha_cambio")
        items = []
        for h in qs:
            items.append({
                "id": str(h.id),
                "estado_anterior": h.estado_anterior,
                "estado_nuevo": h.estado_nuevo,
                "fecha": h.fecha_cambio,
            })
        return Response({"count": len(items), "historial": items}, status=200)
