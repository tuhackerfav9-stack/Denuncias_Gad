import base64
from email.message import EmailMessage

from django.conf import settings
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _gmail_service():
    creds = Credentials(
        token=None,
        refresh_token=settings.GMAIL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GMAIL_CLIENT_ID,
        client_secret=settings.GMAIL_CLIENT_SECRET,
        scopes=GMAIL_SCOPES,
    )
    # fuerza refresh del access token usando el refresh token
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send_gmail_html(to_email: str, subject: str, text_body: str, html_body: str) -> bool:
    try:
        service = _gmail_service()

        msg = EmailMessage()
        msg["To"] = to_email
        msg["From"] = settings.GMAIL_SENDER
        msg["Subject"] = subject

        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        service.users().messages().send(
            userId="me",
            body={"raw": raw},
        ).execute()

        return True
    except Exception as e:
        print("❌ Error Gmail API:", e)
        return False
