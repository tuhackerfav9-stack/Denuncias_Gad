import json
import re
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from openai import OpenAI

from denuncias_api.views_borradores import finalize_borrador_to_denuncia
from denuncias_api.utils_geo import reverse_geocode_nominatim

from db.models import (
    Ciudadanos,
    TiposDenuncia,
    ChatConversaciones,
    ChatMensajes,
    DenunciaBorradores,
)

# =========================================================
# Helpers JWT
# =========================================================
def get_claim(request, key: str, default=None):
    token = getattr(request, "auth", None)
    if token is None:
        return default
    try:
        return token.get(key, default)
    except Exception:
        return default


# =========================================================
# OpenAI client
# =========================================================
def _client():
    return OpenAI(api_key=settings.OPENAI_API_KEY)


# =========================================================
# Tools (Responses API format)
# =========================================================
TOOLS = [
    {
        "type": "function",
        "name": "get_tipos_denuncia",
        "description": "Devuelve los tipos de denuncia disponibles (id, nombre).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "get_borrador",
        "description": "Devuelve el borrador actual (datos_json) para verificar qué falta.",
        "parameters": {
            "type": "object",
            "properties": {"borrador_id": {"type": "string"}},
            "required": ["borrador_id"],
        },
    },
    {
        "type": "function",
        "name": "update_borrador",
        "description": "Actualiza parcialmente campos del borrador.",
        "parameters": {
            "type": "object",
            "properties": {
                "borrador_id": {"type": "string"},
                "tipo_denuncia_id": {"type": "integer"},
                "descripcion": {"type": "string"},
                "referencia": {"type": "string"},
                "direccion_texto": {"type": "string"},
                "latitud": {"type": "number"},
                "longitud": {"type": "number"},
            },
            "required": ["borrador_id"],
        },
    },
    {
        "type": "function",
        "name": "finalizar_denuncia",
        "description": "Finaliza: crea la denuncia (origen=chat) usando el borrador. Devuelve denuncia_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "borrador_id": {"type": "string"},
                "confirmacion": {"type": "boolean"},
            },
            "required": ["borrador_id", "confirmacion"],
        },
    },
]


# =========================================================
# Instrucciones del asistente (NO CAMBIAR)
# =========================================================
INSTRUCTIONS = """
Eres un asistente del GAD Municipal de Salcedo. Ayudas a ciudadanos a redactar denuncias municipales.

Tu objetivo es recolectar estos datos para la denuncia:
- tipo_denuncia_id (obligatorio)
- descripcion (obligatorio)
- latitud y longitud (obligatorio)
- referencia (recomendado, lo escribe el ciudadano: "cerca de...", "frente a...")
- direccion_texto NO la pide al ciudadano: se genera automáticamente por latitud/longitud.

Adjuntos:
- evidencia (foto/video) y firma se envían con botones en la app (no por texto). 
No digas que algo se “subió” a menos que el sistema lo confirme.

Estilo:
- Frases cortas, amables y claras.
- Haz una sola pregunta a la vez.
- Si ya tienes un dato, no lo vuelvas a pedir.

Reglas:
- Si el usuario pregunta algo NO relacionado a denuncias municipales o uso de la app, responde:
  "Solo puedo ayudarte con denuncias municipales y uso de la app 🙂. En este momento no puedo ayudarte con ese tema, pero con gusto te ayudo a registrar tu denuncia."

- Tipos de denuncia:
  Si el usuario pregunta por tipos, está indeciso, o dice “no sé cuál”, llama a la función get_tipos_denuncia y muéstralos numerados para que elija.

- Ubicación:
  Nunca inventes latitud/longitud. Si faltan, pide que envíe su ubicación usando el botón de ubicación (o que envíe un mensaje con lat: X lng: Y).

- Evidencias:
  Pide evidencia (foto/video) cuando sea útil, indicando: elegir foto/video y luego “Subir evidencia”.
  Recuérdale que solo se puede subir evidencia si ya existe un borrador.

- Antes de finalizar:
  Pregunta: "¿Deseas enviar la denuncia ahora? Recuerda que se enviará al instante (sí/no)".
  Solo finaliza si el usuario responde explícitamente "sí" o "enviar".

- Importante:
  Si no se proporcionó borrador_id en el contexto interno, NO llames update_borrador ni finalizar_denuncia; solo conversa y pregunta para recolectar datos.
""".strip()


# =========================================================
# Extractores
# =========================================================
_re_tipo = re.compile(r"(?:^|\b)tipo\s*:\s*([^\n\.]+)", re.IGNORECASE)
_re_desc = re.compile(r"(?:^|\b)(?:descripcion|descripción)\s*:\s*(.+)", re.IGNORECASE)
_re_latlng = re.compile(
    r"(?:lat(?:itud)?)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*.*?(?:lon(?:gitud)?|lng)\s*[:=]?\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE | re.DOTALL,
)
_re_ref = re.compile(r"(?:^|\b)referencia\s*:\s*(.+)", re.IGNORECASE)
_re_dir = re.compile(r"(?:^|\b)(?:direccion|dirección)\s*:\s*(.+)", re.IGNORECASE)

CONFIRM_WORDS = {"si", "sí", "si.", "sí.", "enviar", "confirmo", "confirmo enviar", "enviar denuncia"}
CANCEL_WORDS = {"no", "no.", "cancelar", "anular", "aun no", "aún no"}


def _match_tipo_to_id(nombre: str):
    if not nombre:
        return None

    n = str(nombre).strip().lower()

    if n.isdigit():
        t = TiposDenuncia.objects.filter(activo=True, id=int(n)).first()
        if t:
            return int(t.id)

    qs = TiposDenuncia.objects.filter(activo=True)
    for t in qs:
        if t.nombre:
            tn = t.nombre.strip().lower()
            if tn in n or n in tn:
                return int(t.id)

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

    #   si el usuario dice "dirección:" lo guardamos en referencia
    m = _re_dir.search(text)
    if m:
        out["referencia"] = m.group(1).strip()

    mnum = re.search(r"\b(?:tipo\s*)?([1-9])\b", text.lower())
    if mnum and "tipo_texto" not in out:
        out["tipo_texto"] = mnum.group(1)

    return out


# =========================================================
# Tools backend
# =========================================================
def _execute_tool(uid: str, tool_name: str, args: dict):
    if tool_name == "get_tipos_denuncia":
        qs = TiposDenuncia.objects.filter(activo=True).order_by("nombre")
        return {"tipos": [{"id": int(x.id), "nombre": x.nombre} for x in qs]}

    if tool_name == "get_borrador":
        borrador_id = args["borrador_id"]
        b = DenunciaBorradores.objects.filter(id=borrador_id, ciudadano_id=uid).first()
        if not b:
            return {"error": "borrador_no_existe"}
        return {
            "borrador_id": str(b.id),
            "datos": b.datos_json or {},
            "listo_para_enviar": bool(b.listo_para_enviar),
        }

    if tool_name == "update_borrador":
        borrador_id = args["borrador_id"]
        b = DenunciaBorradores.objects.filter(id=borrador_id, ciudadano_id=uid).first()
        if not b:
            return {"error": "borrador_no_existe"}

        data = b.datos_json or {}

        # 1) Guardar campos normales
        for k in ["tipo_denuncia_id", "descripcion", "referencia", "latitud", "longitud"]:
            if k in args and args[k] is not None:
                data[k] = args[k]

        # 2) Si el modelo manda "direccion_texto", NO lo guardamos ahí:
        #    lo que el ciudadano escribió debe ir a "referencia"
        if "direccion_texto" in args and args["direccion_texto"]:
            if not data.get("referencia"):
                data["referencia"] = args["direccion_texto"]

        # 3) Generar direccion_texto AUTOMÁTICO por lat/lng (reverse geocode)
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

        ok = (
            bool(data.get("tipo_denuncia_id"))
            and bool(data.get("descripcion"))
            and data.get("latitud") is not None
            and data.get("longitud") is not None
        )

        b.datos_json = data
        b.listo_para_enviar = bool(ok)
        b.updated_at = timezone.now()
        b.save(update_fields=["datos_json", "listo_para_enviar", "updated_at"])

        return {"updated": True, "listo_para_enviar": bool(ok), "datos": data}

    if tool_name == "finalizar_denuncia":
        borrador_id = args["borrador_id"]
        confirm = bool(args.get("confirmacion"))

        if not confirm:
            return {"error": "no_confirmado"}

        with transaction.atomic():
            b = DenunciaBorradores.objects.select_for_update().filter(
                id=borrador_id,
                ciudadano_id=uid,
            ).first()
            if not b:
                return {"error": "borrador_no_existe"}

            d = finalize_borrador_to_denuncia(b)
            if not d:
                return {"error": "borrador_incompleto", "datos": (b.datos_json or {})}

        return {"ok": True, "denuncia_id": str(d.id)}

    return {"error": "tool_desconocida"}


# =========================================================
# Historial -> input messages
# =========================================================
def _to_openai_messages(conv_id: str):
    qs = ChatMensajes.objects.filter(conversacion_id=conv_id).order_by("created_at")
    msgs = list(qs)[-30:]
    out = []
    for m in msgs:
        role = "user" if m.emisor == "usuario" else "assistant"
        out.append({"role": role, "content": m.mensaje})
    return out


def _iter_function_calls(resp):
    for item in (resp.output or []):
        if isinstance(item, dict):
            if item.get("type") == "function_call":
                yield {
                    "call_id": item.get("call_id"),
                    "name": item.get("name"),
                    "arguments": item.get("arguments"),
                }
        else:
            if getattr(item, "type", None) == "function_call":
                yield {
                    "call_id": getattr(item, "call_id", None),
                    "name": getattr(item, "name", None),
                    "arguments": getattr(item, "arguments", None),
                }


# =========================================================
# NUEVO helper: crear borrador SOLO cuando haya datos
# =========================================================
def _crear_borrador_si_no_existe(uid: str, conv_id: str):
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


# =========================================================
# Views
# =========================================================
class ChatbotStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")
        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        if not Ciudadanos.objects.filter(usuario_id=uid).exists():
            return Response({"detail": "Perfil ciudadano no existe"}, status=400)

        now = timezone.now()

        #  FIX CLAVE:
        # NO creamos borrador aquí. Solo conversación + mensaje inicial.
        # Así, si el usuario entra/sale del chat SIN escribir nada, NO queda "denuncia vacía".
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

        return Response(
            {"conversacion_id": str(conv.id), "borrador_id": None},
            status=201,
        )


class ChatbotMessageView(APIView):
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

        ChatMensajes.objects.create(
            id=uuid.uuid4(),
            conversacion_id=conv_id,
            emisor="usuario",
            mensaje=text,
            created_at=now,
        )

        texto_norm = text.strip().lower()

        #  Importante: NO crear borrador automáticamente por cualquier mensaje.
        # Solo lo creamos si detectamos datos útiles (tipo/desc/ubicación/ref),
        # o si el usuario intenta "enviar" (porque ya está en flujo de denuncia).
        borr = DenunciaBorradores.objects.filter(conversacion_id=conv_id, ciudadano_id=uid).first()

        extracted = _extract_fields_from_text(text)
        hay_datos_utiles = any(
            k in extracted for k in ("tipo_texto", "descripcion", "latitud", "longitud", "referencia")
        )

        if borr is None and (hay_datos_utiles or (texto_norm in CONFIRM_WORDS)):
            borr = _crear_borrador_si_no_existe(str(uid), str(conv_id))

        # ========= extracción rápida (sin LLM) =========
        if borr is not None and extracted:
            update_payload = {"borrador_id": str(borr.id)}

            if extracted.get("tipo_texto"):
                tipo_id = _match_tipo_to_id(extracted["tipo_texto"])
                if tipo_id:
                    update_payload["tipo_denuncia_id"] = tipo_id

            for k in ["descripcion", "referencia", "latitud", "longitud"]:
                if k in extracted:
                    update_payload[k] = extracted[k]

            if len(update_payload.keys()) > 1:
                _execute_tool(str(uid), "update_borrador", update_payload)
                borr.refresh_from_db()

        # ========= finalizar si listo + confirmación =========
        if borr is not None and borr.listo_para_enviar and texto_norm in CONFIRM_WORDS:
            r = _execute_tool(
                str(uid),
                "finalizar_denuncia",
                {"borrador_id": str(borr.id), "confirmacion": True},
            )

            if r.get("ok"):
                msg_ok = f"  Denuncia enviada. ID: {r['denuncia_id']}"
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
                        "denuncia_id": r["denuncia_id"],
                    },
                    status=200,
                )

            err = r.get("error") or "error_finalizando"
            bot_text = f"❌ No se pudo enviar: {err}. Revisa si falta tipo, descripción o ubicación."
            ChatMensajes.objects.create(
                id=uuid.uuid4(),
                conversacion_id=conv_id,
                emisor="bot",
                mensaje=bot_text,
                created_at=timezone.now(),
            )

            borr2 = DenunciaBorradores.objects.filter(conversacion_id=conv_id, ciudadano_id=uid).first()
            datos = (borr2.datos_json if borr2 else {}) or {}

            return Response(
                {
                    "respuesta": bot_text,
                    "conversacion_id": str(conv_id),
                    "borrador": {
                        "id": str(borr2.id) if borr2 else None,
                        "listo_para_enviar": bool(borr2.listo_para_enviar) if borr2 else False,
                        "datos": datos,
                    },
                },
                status=200,
            )

        # Si el usuario dice "enviar/sí" pero aún NO hay borrador o no está listo, no creamos denuncia vacía:
        if texto_norm in CONFIRM_WORDS and (borr is None or not borr.listo_para_enviar):
            bot_text = (
                "Antes de enviar necesito estos datos: tipo de denuncia, una breve descripción y tu ubicación 📍.\n"
                "Cuéntame qué pasó y envía tu ubicación con el botón de Ubicación."
            )
            ChatMensajes.objects.create(
                id=uuid.uuid4(),
                conversacion_id=conv_id,
                emisor="bot",
                mensaje=bot_text,
                created_at=timezone.now(),
            )
            return Response(
                {
                    "respuesta": bot_text,
                    "conversacion_id": str(conv_id),
                    "borrador": None if borr is None else {
                        "id": str(borr.id),
                        "listo_para_enviar": bool(borr.listo_para_enviar),
                        "datos": (borr.datos_json or {}),
                    },
                },
                status=200,
            )

        # ========= cancelar =========
        if texto_norm in CANCEL_WORDS:
            bot_text = "Está bien 🙂 Cuando quieras continuamos. Si deseas enviar, dime 'sí' o presiona Enviar."
            ChatMensajes.objects.create(
                id=uuid.uuid4(),
                conversacion_id=conv_id,
                emisor="bot",
                mensaje=bot_text,
                created_at=timezone.now(),
            )

            borr2 = DenunciaBorradores.objects.filter(conversacion_id=conv_id, ciudadano_id=uid).first()
            datos = (borr2.datos_json if borr2 else {}) or {}

            return Response(
                {
                    "respuesta": bot_text,
                    "conversacion_id": str(conv_id),
                    "borrador": {
                        "id": str(borr2.id) if borr2 else None,
                        "listo_para_enviar": bool(borr2.listo_para_enviar) if borr2 else False,
                        "datos": datos,
                    } if borr2 else None,
                },
                status=200,
            )

        # ========= LLM =========
        client = _client()
        history = _to_openai_messages(conv_id)

        #   Solo pasamos borrador_id si existe (regla de instrucciones)
        if borr is not None:
            history.append({"role": "user", "content": f"(contexto interno: borrador_id={borr.id})"})
        else:
            history.append({"role": "user", "content": "(contexto interno: borrador_id=None)"})

        resp = client.responses.create(
            model=getattr(settings, "OPENAI_MODEL", "gpt-5"),
            instructions=INSTRUCTIONS,
            tools=TOOLS,
            input=history,
        )

        for _ in range(5):
            calls = list(_iter_function_calls(resp))
            if not calls:
                break

            tool_outputs = []
            for c in calls:
                name = c["name"]
                call_id = c["call_id"]

                try:
                    args = json.loads(c["arguments"] or "{}")
                except Exception:
                    args = {}

                #   seguridad extra: si no hay borrador, no permitimos update/finalize aunque el modelo lo intente
                if borr is None and name in ("update_borrador", "finalizar_denuncia"):
                    result = {"error": "sin_borrador"}
                else:
                    result = _execute_tool(str(uid), name, args)

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )

            resp = client.responses.create(
                model=getattr(settings, "OPENAI_MODEL", "gpt-5"),
                instructions=INSTRUCTIONS,
                tools=TOOLS,
                previous_response_id=resp.id,
                input=tool_outputs,
            )

        bot_text = (resp.output_text or "").strip() or "¿Me confirmas el tipo de denuncia y una breve descripción?"

        # ayuda extra si falta ubicación/evidencia (solo si ya hay borrador)
        borr2 = DenunciaBorradores.objects.filter(conversacion_id=conv_id, ciudadano_id=uid).first()
        if borr2:
            data = borr2.datos_json or {}
            falta_ubic = (data.get("latitud") is None) or (data.get("longitud") is None)
            if falta_ubic and "ubic" not in bot_text.lower():
                bot_text += "\n\n📍 Por favor envía tu ubicación con el botón de Ubicación."
            if "evidencia" not in bot_text.lower():
                bot_text += "\n\n📷 Si tienes, adjunta una foto o video con el botón de Adjuntar."
        else:
            # sin borrador todavía: empuja a dar datos para recién crear uno
            if "ubic" not in bot_text.lower():
                bot_text += "\n\n📍 Cuando estés listo, envía tu ubicación con el botón de Ubicación."

        ChatMensajes.objects.create(
            id=uuid.uuid4(),
            conversacion_id=conv_id,
            emisor="bot",
            mensaje=bot_text,
            created_at=timezone.now(),
        )

        datos = (borr2.datos_json if borr2 else {}) or {}

        return Response(
            {
                "respuesta": bot_text,
                "conversacion_id": str(conv_id),
                "borrador": None if not borr2 else {
                    "id": str(borr2.id),
                    "listo_para_enviar": bool(borr2.listo_para_enviar),
                    "datos": datos,
                },
            },
            status=200,
        )
