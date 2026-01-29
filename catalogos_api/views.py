from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from db.models import TiposDenuncia

class TiposDenunciaView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = TiposDenuncia.objects.filter(activo=True).order_by("nombre")
        data = [{"id": x.id, "nombre": x.nombre, "descripcion": x.descripcion} for x in qs]
        return Response(data, status=200)
