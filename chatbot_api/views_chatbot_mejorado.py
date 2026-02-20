import uuid
import re
from django.db import transaction
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from denuncias_api.views_borradores import finalize_borrador_to_denuncia
from denuncias_api.utils_geo import reverse_geocode_nominatim

from db.models import (
    Ciudadanos,
    TiposDenuncia,
    ChatConversaciones,
    ChatMensajes,
    DenunciaBorradores,
)

# =========================
# JWT helper (igual al tuyo)
# =========================
def get_claim(request, key: str, default=None):
    token = getattr(request, "auth", None)
    if token is None:
        return default
    try:
        return token.get(key, default)
    except Exception:
        return default


# =========================
# Regex extractores (igual idea)
# =========================
_re_tipo = re.compile(r"(?:^|\b)tipo\s*:\s*([^\n\.]+)", re.IGNORECASE)
_re_desc = re.compile(r"(?:^|\b)(?:descripcion|descripción)\s*:\s*(.+)", re.IGNORECASE)
_re_latlng = re.compile(
    r"(?:lat(?:itud)?)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*.*?(?:lon(?:gitud)?|lng)\s*[:=]?\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE | re.DOTALL,
)
_re_ref = re.compile(r"(?:^|\b)referencia\s*:\s*(.+)", re.IGNORECASE)
_re_dir = re.compile(r"(?:^|\b)(?:direccion|dirección)\s*:\s*(.+)", re.IGNORECASE)

CONFIRM_WORDS = {"si", "sí", "si.", "sí.", "enviar", "confirmo", "enviar denuncia"}
CANCEL_WORDS = {"no", "no.", "cancelar", "anular", "aun no", "aún no"}


def _match_tipo_to_id(nombre: str):
    if not nombre:
        return None

    n = str(nombre).strip().lower()

    # si viene número
    if n.isdigit():
        t = TiposDenuncia.objects.filter(activo=True, id=int(n)).first()
        if t:
            return int(t.id)

    # matching por nombre
    qs = TiposDenuncia.objects.filter(activo=True)
    for t in qs:
        tn = (t.nombre or "").strip().lower()
        if tn and (tn in n or n in tn):
            return int(t.id)

    # fallback simple por keyword
    if "basura" in n or "aseo" in n:
        t = TiposDenuncia.objects.filter(activo=True, nombre__icontains="basura").first()
        if t:
            return int(t.id)

    return None


def _extract_fields_from_text(text: str):
    out = {}

    m = _re_tipo.search(text)
    if m:
        out["tipo_texto"] = m.group(1).strip()

    m = _re_desc.search(text)
    if m:
        out["descripcion"] = m.group(1).strip()

    m = _re_latlng.search(text)
    if m:
        out["latitud"] = float(m.group(1))
        out["longitud"] = float(m.group(2))

    m = _re_ref.search(text)
    if m:
        out["referencia"] = m.group(1).strip()

    # si el usuario pone “dirección:” lo guardamos como referencia
    m = _re_dir.search(text)
    if m:
        out["referencia"] = m.group(1).strip()

    return out


def _faltantes(data: dict):
    falt = []
    if not data.get("tipo_denuncia_id"):
        falt.append("tipo_denuncia_id")
    if not data.get("descripcion"):
        falt.append("descripcion")
    if data.get("latitud") is None or data.get("longitud") is None:
        falt.append("ubicacion")
    return falt


def _get_or_create_borrador(uid: str, conv_id: str):
    b = DenunciaBorradores.objects.filter(conversacion_id=conv_id, ciudadano_id=uid).first()
    if b:
        return b

    now = timezone.now()
    return DenunciaBorradores.objects.create(
        id=uuid.uuid4(),
        ciudadano_id=uid,
        conversacion_id=conv_id,
        datos_json={"origen": "chat"},
        listo_para_enviar=False,
        created_at=now,
        updated_at=now,
    )


def _apply_updates_to_borrador(b: DenunciaBorradores, updates: dict):
    data = (b.datos_json or {}).copy()

    # mapeo permitido
    for k in ["tipo_denuncia_id", "descripcion", "referencia", "latitud", "longitud"]:
        if k in updates and updates[k] is not None:
            data[k] = updates[k]

    # direccion_texto solo se genera por reverse
    lat = data.get("latitud")
    lng = data.get("longitud")
    if lat is not None and lng is not None:
        if not data.get("direccion_texto"):
            try:
                dir_txt = reverse_geocode_nominatim(float(lat), float(lng))
                if dir_txt:
                    data["direccion_texto"] = dir_txt
            except Exception:
                pass

    data["origen"] = "chat"

    falt = _faltantes(data)
    b.datos_json = data
    b.listo_para_enviar = (len(falt) == 0)
    b.updated_at = timezone.now()
    b.save(update_fields=["datos_json", "listo_para_enviar", "updated_at"])
    return data, falt


class ChatbotTiposDenunciaV2(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")
        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        qs = TiposDenuncia.objects.filter(activo=True).order_by("nombre")
        return Response(
            {"tipos": [{"id": int(x.id), "nombre": x.nombre} for x in qs]},
            status=200,
        )


class ChatbotStartV2View(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")
        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        if not Ciudadanos.objects.filter(usuario_id=uid).exists():
            return Response({"detail": "Perfil ciudadano no existe"}, status=400)

        now = timezone.now()
        with transaction.atomic():
            conv = ChatConversaciones.objects.create(
                id=uuid.uuid4(),
                ciudadano_id=uid,
                denuncia_id=None,
                created_at=now,
                updated_at=now,
            )
            ChatMensajes.objects.create(
                id=uuid.uuid4(),
                conversacion_id=conv.id,
                emisor="bot",
                mensaje="Hola 👋 ¿Qué deseas denunciar hoy? (Ej: basura, alumbrado, vías...)",
                created_at=now,
            )

        return Response({"conversacion_id": str(conv.id), "borrador_id": None}, status=201)


class ChatbotMessageV2View(APIView):
    """
    V2 = “Sync”:
    - Guarda historial
    - Crea/actualiza borrador si hay datos útiles
    - Finaliza si está listo y usuario confirma
    - Si Flutter manda bot_response (Gemini), lo guardamos como mensaje del bot
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")
        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        conv_id = (request.data.get("conversacion_id") or "").strip()
        text = (request.data.get("mensaje") or "").strip()
        if not conv_id or not text:
            return Response({"detail": "conversacion_id y mensaje son obligatorios"}, status=400)

        conv = ChatConversaciones.objects.filter(id=conv_id, ciudadano_id=uid).first()
        if not conv:
            return Response({"detail": "Conversación no existe"}, status=404)

        now = timezone.now()

        # 1) guardar msg usuario
        ChatMensajes.objects.create(
            id=uuid.uuid4(),
            conversacion_id=conv_id,
            emisor="usuario",
            mensaje=text,
            created_at=now,
        )

        texto_norm = text.strip().lower()

        # 2) updates desde Flutter (opcional)
        extracted_client = request.data.get("extracted") or {}
        if not isinstance(extracted_client, dict):
            extracted_client = {}

        # 3) updates desde texto (siempre)
        extracted_text = _extract_fields_from_text(text)

        # 4) decidir si creamos borrador
        borr = DenunciaBorradores.objects.filter(conversacion_id=conv_id, ciudadano_id=uid).first()

        hay_datos_utiles = any(
            k in extracted_text for k in ("tipo_texto", "descripcion", "latitud", "longitud", "referencia")
        ) or any(
            k in extracted_client for k in ("tipo_denuncia_id", "descripcion", "latitud", "longitud", "referencia")
        )

        if borr is None and (hay_datos_utiles or (texto_norm in CONFIRM_WORDS)):
            borr = _get_or_create_borrador(str(uid), str(conv_id))

        falt = []
        data = {}

        # 5) aplicar updates si hay borrador
        if borr is not None:
            updates = {}

            # tipo: preferir id directo del cliente
            if extracted_client.get("tipo_denuncia_id"):
                updates["tipo_denuncia_id"] = int(extracted_client["tipo_denuncia_id"])
            elif extracted_client.get("tipo_texto"):
                tid = _match_tipo_to_id(extracted_client["tipo_texto"])
                if tid:
                    updates["tipo_denuncia_id"] = tid
            elif extracted_text.get("tipo_texto"):
                tid = _match_tipo_to_id(extracted_text["tipo_texto"])
                if tid:
                    updates["tipo_denuncia_id"] = tid

            # otros campos (cliente pisa a texto si vienen)
            for k in ["descripcion", "referencia", "latitud", "longitud"]:
                if k in extracted_text:
                    updates[k] = extracted_text[k]
                if k in extracted_client and extracted_client[k] is not None:
                    updates[k] = extracted_client[k]

            data, falt = _apply_updates_to_borrador(borr, updates)

        # 6) finalizar si listo + confirmación
        if borr is not None and borr.listo_para_enviar and (texto_norm in CONFIRM_WORDS):
            with transaction.atomic():
                b = DenunciaBorradores.objects.select_for_update().filter(
                    id=borr.id, ciudadano_id=uid
                ).first()
                if not b:
                    return Response({"detail": "borrador_no_existe"}, status=404)

                d = finalize_borrador_to_denuncia(b)
                if not d:
                    return Response(
                        {"detail": "borrador_incompleto", "faltantes": _faltantes(b.datos_json or {})},
                        status=400,
                    )

            msg_ok = f"✅ Denuncia enviada. ID: {d.id}"
            ChatMensajes.objects.create(
                id=uuid.uuid4(),
                conversacion_id=conv_id,
                emisor="bot",
                mensaje=msg_ok,
                created_at=timezone.now(),
            )
            return Response(
                {
                    "respuesta": msg_ok,
                    "conversacion_id": str(conv_id),
                    "denuncia_id": str(d.id),
                    "borrador": {
                        "id": str(borr.id),
                        "listo_para_enviar": True,
                        "datos": (borr.datos_json or {}),
                        "faltantes": [],
                    },
                    "source": "server",
                },
                status=200,
            )

        # 7) guardar respuesta del bot que manda Flutter (Gemini)
        bot_response = request.data.get("bot_response")
        if isinstance(bot_response, str) and bot_response.strip():
            ChatMensajes.objects.create(
                id=uuid.uuid4(),
                conversacion_id=conv_id,
                emisor="bot",
                mensaje=bot_response.strip(),
                created_at=timezone.now(),
            )
            respuesta = bot_response.strip()
            source = "gemini"
        else:
            # 8) fallback server simple (por si Gemini falla)
            if texto_norm in CANCEL_WORDS:
                respuesta = "Está bien 🙂 Cuando quieras continuamos. Si deseas enviar, dime 'sí' o presiona Enviar."
            elif borr is None:
                respuesta = "Cuéntame qué pasó (una breve descripción) y, si puedes, envía tu ubicación 📍."
            else:
                if "tipo_denuncia_id" in falt:
                    respuesta = "¿Qué tipo de denuncia es? Si no sabes, dime “tipos” y te muestro la lista."
                elif "descripcion" in falt:
                    respuesta = "Descríbeme brevemente qué pasó."
                elif "ubicacion" in falt:
                    respuesta = "📍 Envíame tu ubicación con el botón de Ubicación."
                else:
                    respuesta = "¿Deseas enviar la denuncia ahora? (sí/no)"
            source = "server"

            ChatMensajes.objects.create(
                id=uuid.uuid4(),
                conversacion_id=conv_id,
                emisor="bot",
                mensaje=respuesta,
                created_at=timezone.now(),
            )

        return Response(
            {
                "respuesta": respuesta,
                "conversacion_id": str(conv_id),
                "borrador": None if borr is None else {
                    "id": str(borr.id),
                    "listo_para_enviar": bool(borr.listo_para_enviar),
                    "datos": (borr.datos_json or {}),
                    "faltantes": falt,
                },
                "source": source,
            },
            status=200,
        )
