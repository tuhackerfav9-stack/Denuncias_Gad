# denuncias_api/views_respuestas.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

  
from db.models import Denuncias, DenunciaRespuestas

from .utils import get_claim

class DenunciaRespuestasView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, denuncia_id):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")
        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        # Seguridad: que la denuncia sea del ciudadano
        try:
            d = Denuncias.objects.get(id=denuncia_id, ciudadano_id=uid)
        except Denuncias.DoesNotExist:
            return Response({"detail": "Denuncia no existe"}, status=404)

        qs = DenunciaRespuestas.objects.filter(denuncia_id=d.id).order_by("created_at")
        data = []
        for r in qs:
            data.append({
                "id": str(r.id),
                "mensaje": r.mensaje,
                "fecha": r.created_at.isoformat() if r.created_at else None,
                "funcionario": {
                    "id": str(r.funcionario_id) if r.funcionario_id else None,
                    "nombre": getattr(r.funcionario, "nombres", "") if r.funcionario else "",
                    "apellido": getattr(r.funcionario, "apellidos", "") if r.funcionario else "",
                }
            })

        return Response({"count": len(data), "respuestas": data}, status=200)


