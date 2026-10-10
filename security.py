"""Small production-preparation helpers; not a substitute for managed edge protection."""
import os, smtplib, ssl, time, threading
from email.message import EmailMessage
from collections import defaultdict, deque
_lock=threading.Lock(); _hits=defaultdict(deque)
def allowed(key, max_hits=8, window=3600):
    now=time.monotonic()
    with _lock:
        q=_hits[key]
        while q and now-q[0]>window:q.popleft()
        if len(q)>=max_hits:return False
        q.append(now)
        return True

def notify(subject, message):
    """Optional SMTP notification; returns False when not configured."""
    host=os.getenv('RM_SMTP_HOST'); recipient=os.getenv('RM_NOTIFY_EMAIL'); sender=os.getenv('RM_SMTP_FROM')
    if not all((host,recipient,sender)):return False
    email=EmailMessage();email['Subject']=subject;email['From']=sender;email['To']=recipient;email.set_content(message)
    port=int(os.getenv('RM_SMTP_PORT','465'))
    with smtplib.SMTP_SSL(host,port,context=ssl.create_default_context(),timeout=10) as smtp:
        if os.getenv('RM_SMTP_USER'):smtp.login(os.getenv('RM_SMTP_USER'),os.getenv('RM_SMTP_PASSWORD',''))
        smtp.send_message(email)
    return True
