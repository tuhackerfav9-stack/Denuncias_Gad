import os
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings

_initialized = False

def init_firebase():
    global _initialized
    if _initialized:
        return

    path = str(getattr(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", "")).strip()
    print("[FCM] path:", path)

    if not path or not os.path.exists(path):
        print(f"[FCM] Service account no encontrado: {path}. Push deshabilitado.")
        _initialized = True
        return

    try:
        cred = credentials.Certificate(path)
        firebase_admin.initialize_app(cred)
        print("[FCM] inicializado OK")
    except Exception as e:
        print("[FCM] init error:", e)
    finally:
        _initialized = True

def send_push(tokens: list[str], title: str, body: str, data: dict | None = None):
    if not tokens:
        return 0

    init_firebase()

    # si no hay app inicializada (porque faltó el json), salimos sin romper
    if not firebase_admin._apps:
        return 0

    messages = [
        messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=t,
        )
        for t in tokens
    ]

    try:
        resp = messaging.send_each(messages)
        for r, tok in zip(resp.responses, tokens):
            if not r.success:
                print("FCM ERROR token:", tok, "=>", r.exception)
        return resp.success_count
    except Exception as e:
        print("[FCM] Error enviando push:", e)
        return 0
