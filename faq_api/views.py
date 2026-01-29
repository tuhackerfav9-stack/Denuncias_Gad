from django.shortcuts import render

# Create your views here.
from django.db.models import Q
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from db.models import Faq
from .serializers import FaqListSerializer, FaqCreateUpdateSerializer
from .permissions import IsAdminTIC


class FaqListCreateView(APIView):
    """
    GET: ciudadano ve FAQ visibles (o admin ve todo si quieres)
    POST: solo Admin TIC crea
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()

        qs = Faq.objects.filter(visible=True).order_by("-updated_at", "-created_at")

        if q:
            qs = qs.filter(
                Q(pregunta__icontains=q) |
                Q(respuesta__icontains=q)
            )

        data = FaqListSerializer(qs, many=True).data
        return Response(data, status=200)

    def post(self, request):
        # solo admin
        if not IsAdminTIC().has_permission(request, self):
            return Response({"detail": "Solo Admin TIC"}, status=403)

        ser = FaqCreateUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        now = timezone.now()
        obj = Faq.objects.create(
            pregunta=ser.validated_data["pregunta"],
            respuesta=ser.validated_data["respuesta"],
            visible=ser.validated_data.get("visible", True),
            creado_por_id=getattr(request.auth, "get", lambda k, d=None: None)("uid", None),
            created_at=now,
            updated_at=now,
        )

        return Response(FaqListSerializer(obj).data, status=201)


class FaqDetailView(APIView):
    """
    GET: ciudadano ve si visible
    PATCH/PUT/DELETE: solo Admin TIC
    """
    permission_classes = [IsAuthenticated]

    def get_obj(self, faq_id):
        return Faq.objects.get(id=faq_id)

    def get(self, request, faq_id):
        try:
            obj = self.get_obj(faq_id)
        except Faq.DoesNotExist:
            return Response({"detail": "No existe"}, status=404)

        if not obj.visible:
            # si no es admin, no lo muestres
            if not IsAdminTIC().has_permission(request, self):
                return Response({"detail": "No existe"}, status=404)

        return Response(FaqListSerializer(obj).data, status=200)

    def patch(self, request, faq_id):
        return self._update(request, faq_id, partial=True)

    def put(self, request, faq_id):
        return self._update(request, faq_id, partial=False)

    def _update(self, request, faq_id, partial: bool):
        if not IsAdminTIC().has_permission(request, self):
            return Response({"detail": "Solo Admin TIC"}, status=403)

        try:
            obj = self.get_obj(faq_id)
        except Faq.DoesNotExist:
            return Response({"detail": "No existe"}, status=404)

        ser = FaqCreateUpdateSerializer(obj, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)

        for k, v in ser.validated_data.items():
            setattr(obj, k, v)
        obj.updated_at = timezone.now()
        obj.save()

        return Response(FaqListSerializer(obj).data, status=200)

    def delete(self, request, faq_id):
        if not IsAdminTIC().has_permission(request, self):
            return Response({"detail": "Solo Admin TIC"}, status=403)

        try:
            obj = self.get_obj(faq_id)
        except Faq.DoesNotExist:
            return Response({"detail": "No existe"}, status=404)

        obj.delete()
        return Response({"detail": "Eliminado"}, status=200)
