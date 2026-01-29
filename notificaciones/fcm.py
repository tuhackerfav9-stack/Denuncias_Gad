import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings

_initialized = False

def init_firebase():
    global _initialized
    if _initialized:
        return
    cred = credentials.Certificate(str(settings.FIREBASE_SERVICE_ACCOUNT_PATH))
    firebase_admin.initialize_app(cred)
    _initialized = True

def send_push(tokens: list[str], title: str, body: str, data: dict | None = None):
    if not tokens:
        return 0

    init_firebase()

    messages = []
    for t in tokens:
        messages.append(
            messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
                token=t,
            )
        )

    resp = messaging.send_each(messages)  # ✅
    # opcional: imprime errores por token
    for r, tok in zip(resp.responses, tokens):
        if not r.success:
            print("FCM ERROR token:", tok, "=>", r.exception)

    return resp.success_count
