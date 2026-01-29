import uuid
from datetime import timedelta

from django.utils import timezone
from django.db import transaction

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from db.models import Ciudadanos, Denuncias, DenunciaBorradores

from .serializers_borradores import (
    DenunciaBorradorCreateSerializer,
    DenunciaBorradorUpdateSerializer,
)

from db.models import DenunciaEvidencias, DenunciaFirmas
import requests

def reverse_geocode_nominatim(lat: float, lng: float) -> str | None:
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "format": "jsonv2",
            "lat": lat,
            "lon": lng,
            "zoom": 18,
            "addressdetails": 1,
        }
        headers = {"User-Agent": "DenunciasSalcedo/1.0 (contacto: admin@gad.gob.ec)"}
        r = requests.get(url, params=params, headers=headers, timeout=6)
        if r.status_code != 200:
            return None
        data = r.json()
        return data.get("display_name")
    except Exception:
        return None

# =========================
# Helpers
# =========================
def get_claim(request, key: str, default=None):
    token = getattr(request, "auth", None)
    if token is None:
        return default
    try:
        return token.get(key, default)
    except Exception:
        return default


BORRADOR_TTL_MIN = 5


def expires_at(b):
    return b.created_at + timedelta(minutes=BORRADOR_TTL_MIN)


def borrador_expirado(b):
    return timezone.now() >= expires_at(b)


def seconds_left(b):
    s = int((expires_at(b) - timezone.now()).total_seconds())
    return max(0, s)


def finalize_borrador_to_denuncia(b: DenunciaBorradores):
    """
    Convierte borrador -> denuncia definitiva y BORRA el borrador.
    """
    data = b.datos_json or {}
    now = timezone.now()

    tipo_denuncia_id = data.get("tipo_denuncia_id")
    descripcion = data.get("descripcion")
    latitud = data.get("latitud")
    longitud = data.get("longitud")

    # Validación mínima
    if not tipo_denuncia_id or not descripcion or latitud is None or longitud is None:
        return None

    denuncia = Denuncias.objects.create(
        id=uuid.uuid4(),
        ciudadano_id=b.ciudadano_id,
        tipo_denuncia_id=tipo_denuncia_id,
        descripcion=descripcion,
        referencia=data.get("referencia"),
        latitud=latitud,
        longitud=longitud,
        direccion_texto=data.get("direccion_texto"),
        origen=data.get("origen", "formulario"),
        estado="pendiente",
        created_at=now,
        updated_at=now,
    )
        # ===== firma =====
    firma_url = data.get("firma_url")
    firma_base64 = data.get("firma_base64")  # por si luego usas base64

    if firma_url or firma_base64:
        DenunciaFirmas.objects.create(
            id=uuid.uuid4(),
            denuncia_id=denuncia.id,
            firma_url=firma_url,
            firma_base64=firma_base64,
            created_at=now,
            updated_at=now,
        )

    # ===== evidencias =====
    evidencias = data.get("evidencias") or []
    for ev in evidencias:
        try:
            DenunciaEvidencias.objects.create(
                id=uuid.uuid4(),
                denuncia_id=denuncia.id,
                tipo=(ev.get("tipo") or "foto"),
                url_archivo=(ev.get("url_archivo") or ""),
                nombre_archivo=ev.get("nombre_archivo"),
                created_at=now,
                updated_at=now,
            )
        except Exception:
            pass


    # Si viene de chat (opcional)
    if b.conversacion_id:
        try:
            conv = b.conversacion
            conv.denuncia_id = denuncia.id
            conv.updated_at = now
            conv.save(update_fields=["denuncia_id", "updated_at"])
        except Exception:
            pass

    b.delete()
    return denuncia


# =========================
# Views
# =========================
class BorradoresCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")

        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        if not Ciudadanos.objects.filter(usuario_id=uid).exists():
            return Response({"detail": "Perfil ciudadano no existe"}, status=400)

        
        ser = DenunciaBorradorCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data

        now = timezone.now()
        data = dict(v)  # lo guardamos tal cual
        data["origen"] = data.get("origen", "formulario")

        if not data.get("direccion_texto"):
            data["direccion_texto"] = reverse_geocode_nominatim(data["latitud"], data["longitud"])

        b = DenunciaBorradores.objects.create(
            id=uuid.uuid4(),
            ciudadano_id=uid,
            conversacion_id=None,
            datos_json=data,
            listo_para_enviar=False,
            created_at=now,
            updated_at=now,
        )

        return Response(
            {
                "detail": "Borrador creado",
                "borrador_id": str(b.id),
                "expira_en_seg": seconds_left(b),
                "expira_en_min": BORRADOR_TTL_MIN,
                "editable": True,
            },
            status=201
        )


class BorradoresUpdateDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, borrador_id):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")
        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        try:
            b = DenunciaBorradores.objects.get(id=borrador_id, ciudadano_id=uid)
        except DenunciaBorradores.DoesNotExist:
            return Response({"detail": "Borrador no existe"}, status=404)

        if borrador_expirado(b):
            return Response({"detail": "Borrador expirado: ya no se puede editar"}, status=409)

        #  UPDATE PARCIAL (solo lo que cambie)
        ser = DenunciaBorradorUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data

        data = b.datos_json or {}
        data.update(v)

        b.datos_json = data
        b.updated_at = timezone.now()
        b.save(update_fields=["datos_json", "updated_at"])

        return Response(
            {
                "detail": "Borrador actualizado",
                "expira_en_seg": seconds_left(b),
                "editable": True,
            },
            status=200
        )

    def delete(self, request, borrador_id):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")
        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        try:
            b = DenunciaBorradores.objects.get(id=borrador_id, ciudadano_id=uid)
        except DenunciaBorradores.DoesNotExist:
            return Response({"detail": "Borrador no existe"}, status=404)

        if borrador_expirado(b):
            return Response({"detail": "Borrador expirado: ya no se puede eliminar"}, status=409)

        b.delete()
        return Response({"detail": "Borrador eliminado"}, status=200)


class BorradoresMiosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")
        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        qs = list(DenunciaBorradores.objects.filter(ciudadano_id=uid).order_by("-created_at"))

        finalizados_auto = 0
        borradores = []

        for b in qs:
            if borrador_expirado(b):
                with transaction.atomic():
                    # lock para evitar carrera
                    try:
                        b_lock = DenunciaBorradores.objects.select_for_update().get(id=b.id)
                    except DenunciaBorradores.DoesNotExist:
                        continue
                    d = finalize_borrador_to_denuncia(b_lock)
                    if d:
                        finalizados_auto += 1
                continue

            data = b.datos_json or {}
            borradores.append({
                "id": str(b.id),
                "expira_en_seg": seconds_left(b),
                "expira_en_min": BORRADOR_TTL_MIN,
                "editable": True,
                **data
            })

        return Response(
            {"finalizados_auto": finalizados_auto, "borradores": borradores},
            status=200
        )


class BorradoresFinalizarManualView(APIView):
    """
    Si luego quieres “Enviar ya” antes de los 5 min, lo dejamos disponible.
    Por ahora simplemente finaliza y crea denuncia.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, borrador_id):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")
        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        try:
            b = DenunciaBorradores.objects.get(id=borrador_id, ciudadano_id=uid)
        except DenunciaBorradores.DoesNotExist:
            return Response({"detail": "Borrador no existe"}, status=404)

        with transaction.atomic():
            b = DenunciaBorradores.objects.select_for_update().get(id=b.id)
            d = finalize_borrador_to_denuncia(b)
            if not d:
                return Response({"detail": "Borrador incompleto, no se pudo finalizar"}, status=409)

        return Response({"detail": "Borrador finalizado", "denuncia_id": str(d.id)}, status=201)
