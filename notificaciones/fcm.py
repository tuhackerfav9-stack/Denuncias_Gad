import os
import logging
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings

logger = logging.getLogger(__name__)

_initialized = False


def init_firebase():
    global _initialized

    if _initialized:
        return

    path = str(getattr(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", "")).strip()
    logger.info(f"[FCM] Service account path: {path}")

    if not path or not os.path.exists(path):
        logger.warning(f"[FCM] Service account no encontrado: {path}. Push deshabilitado.")
        _initialized = True
        return

    try:
        cred = credentials.Certificate(path)
        firebase_admin.initialize_app(cred)
        logger.info("[FCM] Inicializado correctamente")
    except Exception as e:
        logger.exception(f"[FCM] Error inicializando Firebase: {e}")
    finally:
        _initialized = True


def send_push(tokens: list[str], title: str, body: str, data: dict | None = None) -> int:
    if not tokens:
        return 0

    init_firebase()

    # Si Firebase no se inicializó (por ejemplo falta el JSON)
    if not firebase_admin._apps:
        logger.warning("[FCM] Firebase no inicializado. Push omitido.")
        return 0

    messages = [
        messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=token,
        )
        for token in tokens
    ]

    try:
        response = messaging.send_each(messages)

        bad_tokens = []

        for resp, token in zip(response.responses, tokens):
            if not resp.success:
                error_msg = str(resp.exception).lower()
                logger.warning(f"[FCM] Error token {token}: {resp.exception}")

                # Tokens inválidos o no registrados
                if any(err in error_msg for err in [
                    "requested entity was not found",
                    "unregistered",
                    "not found",
                    "invalid registration token"
                ]):
                    bad_tokens.append(token)

        # 🔥 Eliminación automática de tokens inválidos
        if bad_tokens:
            from notificaciones.models import DeviceToken  # Ajusta si es necesario
            deleted_count, _ = DeviceToken.objects.filter(
                fcm_token__in=bad_tokens
            ).delete()

            logger.info(f"[FCM] Tokens inválidos eliminados: {deleted_count}")

        return response.success_count

    except Exception as e:
        logger.exception(f"[FCM] Error enviando push: {e}")
        return 0
