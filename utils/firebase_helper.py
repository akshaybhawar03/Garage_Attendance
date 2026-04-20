"""
Firebase Cloud Messaging push notifications.
"""

import os
import json
import firebase_admin
from firebase_admin import credentials, messaging
from dotenv import load_dotenv

load_dotenv()

_app = None


def init_firebase():
    """Initialise the Firebase Admin SDK (safe to call multiple times)."""
    global _app
    if _app is not None:
        return

    sa_path = os.getenv("FIREBASE_SERVICE_ACCOUNT", "serviceAccount.json")

    if os.path.exists(sa_path):
        cred = credentials.Certificate(sa_path)
    else:
        raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
        if raw:
            cred = credentials.Certificate(json.loads(raw))
        else:
            return  # Firebase not configured — skip silently

    _app = firebase_admin.initialize_app(cred)


def send_notification(token: str, title: str, body: str) -> bool:
    """Send a push notification via FCM.  Returns True on success."""
    if _app is None:
        return False
    try:
        msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            token=token,
        )
        messaging.send(msg)
        return True
    except Exception:
        return False
