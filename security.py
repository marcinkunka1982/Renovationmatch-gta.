
import os
import json
import time
import threading
import urllib.request
from collections import defaultdict, deque

_lock = threading.Lock()
_hits = defaultdict(deque)

def allowed(key, max_hits=8, window=3600):
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= max_hits:
            return False
        q.append(now)
        return True

def notify(subject, message):
    api_key = os.getenv("RESEND_API_KEY")
    recipient = os.getenv("RM_NOTIFY_EMAIL")
    sender = os.getenv("RM_RESEND_FROM", "onboarding@resend.dev")

    if not api_key or not recipient:
        return False

    payload = json.dumps({
        "from": sender,
        "to": [recipient],
        "subject": subject,
        "text": message
    }).encode("utf-8")

    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=15) as response:
        return response.status == 200
