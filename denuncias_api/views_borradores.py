# denuncias_api/views_borradores.py

import uuid
from datetime import timedelta

import requests
from django.db import transaction
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from db.models import (
    Ciudadanos,
    Denuncias,
    DenunciaBorradores,
    DenunciaEvidencias,
    DenunciaFirmas,
    BorradorArchivo,
    DenunciaArchivo,
)

from .serializers_borradores import (
    DenunciaBorradorCreateSerializer,
    DenunciaBorradorUpdateSerializer,
)

from .utils import get_claim


# =========================================================
# GEO
# =========================================================
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


# =========================================================
# TTL Borrador
# =========================================================
BORRADOR_TTL_MIN = 5


def expires_at(b: DenunciaBorradores):
    return b.created_at + timedelta(minutes=BORRADOR_TTL_MIN)


def borrador_expirado(b: DenunciaBorradores):
    return timezone.now() >= expires_at(b)


def seconds_left(b: DenunciaBorradores):
    s = int((expires_at(b) - timezone.now()).total_seconds())
    return max(0, s)


# =========================================================
# FINALIZE: borrador -> denuncia
# =========================================================
def finalize_borrador_to_denuncia(b: DenunciaBorradores):
    """
    Convierte borrador -> denuncia definitiva y BORRA el borrador.
    - Soporta BIN (BorradorArchivo -> DenunciaArchivo)
    - Soporta MEDIA viejo (url_archivo y firma_url ya guardados)
    """
    data = b.datos_json or {}
    now = timezone.now()

    # -------- Validación mínima --------
    tipo_denuncia_id = data.get("tipo_denuncia_id")
    descripcion = data.get("descripcion")
    latitud = data.get("latitud")
    longitud = data.get("longitud")

    if not tipo_denuncia_id or not descripcion or latitud is None or longitud is None:
        return None

    # -------- 1) Crear denuncia --------
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

    # -------- 2) Firma (BIN o viejo) --------
    firma_archivo_id = data.get("firma_archivo_id")

    if firma_archivo_id:
        try:
            ba = BorradorArchivo.objects.get(id=firma_archivo_id, borrador_id=b.id)

            da = DenunciaArchivo.objects.create(
                id=uuid.uuid4(), #id
                denuncia_id=denuncia.id,
                tipo="firma",
                filename=ba.filename,
                content_type=ba.content_type,
                size_bytes=ba.size_bytes,
                data=ba.data,
            )

            # URL RELATIVA (tu app está montada en /api/denuncias/)
            firma_url_rel = f"/api/denuncias/archivos/denuncia/{da.id}/"

            DenunciaFirmas.objects.create(
                id=uuid.uuid4(),
                denuncia_id=denuncia.id,
                firma_url=firma_url_rel,
                firma_base64=None,
                created_at=now,
                updated_at=now,
            )
        except Exception:
            # no cortamos el flujo por firma
            pass
    else:
        # Firma modo viejo (por si aún existe)
        firma_url = data.get("firma_url")
        firma_base64 = data.get("firma_base64")
        if firma_url or firma_base64:
            try:
                DenunciaFirmas.objects.create(
                    id=uuid.uuid4(),
                    denuncia_id=denuncia.id,
                    firma_url=firma_url,
                    firma_base64=firma_base64,
                    created_at=now,
                    updated_at=now,
                )
            except Exception:
                pass

    # -------- 3) Evidencias (BIN o viejo) --------
    evidencias = data.get("evidencias") or []
    for ev in evidencias:
        try:
            ev_tipo = (ev.get("tipo") or "foto")

            # BIN: viene archivo_id
            archivo_id = ev.get("archivo_id")
            if archivo_id:
                ba = BorradorArchivo.objects.get(id=archivo_id, borrador_id=b.id)

                da = DenunciaArchivo.objects.create(
                    id=uuid.uuid4(), #id
                    denuncia_id=denuncia.id,
                    tipo=(ev_tipo or ba.tipo or "foto"),
                    filename=ba.filename,
                    content_type=ba.content_type,
                    size_bytes=ba.size_bytes,
                    data=ba.data,
                )

                url_rel = f"/api/denuncias/archivos/denuncia/{da.id}/"

                DenunciaEvidencias.objects.create(
                    id=uuid.uuid4(),
                    denuncia_id=denuncia.id,
                    tipo=(ev_tipo or "foto"),
                    url_archivo=url_rel,
                    nombre_archivo=(ba.filename or ev.get("nombre_archivo")),
                    created_at=now,
                    updated_at=now,
                )
                continue

            # MEDIA viejo: ya trae url_archivo
            DenunciaEvidencias.objects.create(
                id=uuid.uuid4(),
                denuncia_id=denuncia.id,
                tipo=(ev_tipo or "foto"),
                url_archivo=(ev.get("url_archivo") or ""),
                nombre_archivo=ev.get("nombre_archivo"),
                created_at=now,
                updated_at=now,
            )
        except Exception:
            pass

    # -------- 4) Si viene de chat: linkear conversación -> denuncia --------
    if getattr(b, "conversacion_id", None):
        try:
            conv = b.conversacion
            conv.denuncia_id = denuncia.id
            conv.updated_at = now
            conv.save(update_fields=["denuncia_id", "updated_at"])
        except Exception:
            pass

    # -------- 5) Limpieza: borrar archivos bin del borrador + borrar borrador --------
    try:
        BorradorArchivo.objects.filter(borrador_id=b.id).delete()
    except Exception:
        pass

    b.delete()
    return denuncia


# =========================================================
# Views
# =========================================================
class BorradoresCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")

        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=status.HTTP_403_FORBIDDEN)

        if not Ciudadanos.objects.filter(usuario_id=uid).exists():
            return Response({"detail": "Perfil ciudadano no existe"}, status=status.HTTP_400_BAD_REQUEST)

        ser = DenunciaBorradorCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data

        now = timezone.now()
        data = dict(v)
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
            status=status.HTTP_201_CREATED
        )


class BorradoresUpdateDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, borrador_id):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")

        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=status.HTTP_403_FORBIDDEN)

        try:
            b = DenunciaBorradores.objects.get(id=borrador_id, ciudadano_id=uid)
        except DenunciaBorradores.DoesNotExist:
            return Response({"detail": "Borrador no existe"}, status=status.HTTP_404_NOT_FOUND)

        if borrador_expirado(b):
            return Response({"detail": "Borrador expirado: ya no se puede editar"}, status=status.HTTP_409_CONFLICT)

        ser = DenunciaBorradorUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data

        data = b.datos_json or {}
        data.update(v)

        b.datos_json = data
        b.updated_at = timezone.now()
        b.save(update_fields=["datos_json", "updated_at"])

        return Response(
            {"detail": "Borrador actualizado", "expira_en_seg": seconds_left(b), "editable": True},
            status=status.HTTP_200_OK
        )

    def delete(self, request, borrador_id):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")

        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=status.HTTP_403_FORBIDDEN)

        try:
            b = DenunciaBorradores.objects.get(id=borrador_id, ciudadano_id=uid)
        except DenunciaBorradores.DoesNotExist:
            return Response({"detail": "Borrador no existe"}, status=status.HTTP_404_NOT_FOUND)

        if borrador_expirado(b):
            return Response({"detail": "Borrador expirado: ya no se puede eliminar"}, status=status.HTTP_409_CONFLICT)

        try:
            BorradorArchivo.objects.filter(borrador_id=b.id).delete()
        except Exception:
            pass

        b.delete()
        return Response({"detail": "Borrador eliminado"}, status=status.HTTP_200_OK)


class BorradoresMiosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")

        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=status.HTTP_403_FORBIDDEN)

        qs = list(DenunciaBorradores.objects.filter(ciudadano_id=uid).order_by("-created_at"))

        finalizados_auto = 0
        borradores = []

        for b in qs:
            if borrador_expirado(b):
                with transaction.atomic():
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

        return Response({"finalizados_auto": finalizados_auto, "borradores": borradores}, status=status.HTTP_200_OK)


class BorradoresFinalizarManualView(APIView):
    """
    Finalizar manual antes de expirar (crear denuncia ya).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, borrador_id):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")

        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=status.HTTP_403_FORBIDDEN)

        try:
            b = DenunciaBorradores.objects.get(id=borrador_id, ciudadano_id=uid)
        except DenunciaBorradores.DoesNotExist:
            return Response({"detail": "Borrador no existe"}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            b = DenunciaBorradores.objects.select_for_update().get(id=b.id)
            d = finalize_borrador_to_denuncia(b)
            if not d:
                return Response(
                    {"detail": "Borrador incompleto, no se pudo finalizar"},
                    status=status.HTTP_409_CONFLICT
                )

        return Response(
            {"detail": "Borrador finalizado", "denuncia_id": str(d.id)},
            status=status.HTTP_201_CREATED
        )
