import hashlib
import json
import os
import secrets
import smtplib
import ssl
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

def install(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS calendar_feeds(shop TEXT PRIMARY KEY, digest TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS customer_keys(ref TEXT PRIMARY KEY, digest TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS mail_queue(id INTEGER PRIMARY KEY, recipient TEXT, subject TEXT,
        body TEXT, attempts INTEGER DEFAULT 0, available REAL DEFAULT 0, lease TEXT);
    """)

def digest(key):
    return hashlib.sha256(key.encode()).hexdigest()

def new_key(db, ref):
    key=secrets.token_urlsafe(32)
    db.execute("INSERT INTO customer_keys VALUES (?,?)",(ref,digest(key)))
    return key

def lookup(db, shop, ref, key):
    row=db.execute("SELECT b.*,k.digest FROM bookings b JOIN customer_keys k ON k.ref=b.ref WHERE b.shop=? AND b.ref=?",(shop,ref)).fetchone()
    return row if row and secrets.compare_digest(row["digest"],digest(key)) else None

def notice(db, booking, subject, key=None):
    body=f'{booking["service"]}\n{booking["day"]} · {booking["label"]} (Amsterdam time)\nBooking reference {booking["ref"]}'
    config=json.loads(db.execute("SELECT config FROM shops WHERE slug=?",(booking["shop"],)).fetchone()[0])
    extra=config.get("mailText","")
    for token,field in {"customer_name":"name","service_name":"service","booking_date":"day","booking_time":"label","booking_price":"price"}.items():
        extra=extra.replace("{{"+token+"}}",booking[field])
    if extra.strip():
        body+="\n\n"+extra
    base=os.environ.get("BLENDBOOK_PUBLIC_URL","").rstrip("/")
    if key and base.startswith("https://"):
        body+=f'\n\nManage your booking: {base}/manage#{booking["shop"]}/{booking["ref"]}/{key}'
    db.execute("INSERT INTO mail_queue(recipient,subject,body) VALUES (?,?,?)",(booking["email"],subject,body))

def deliver(db):
    host=os.environ["BLENDBOOK_SMTP_HOST"]
    sender=os.environ["BLENDBOOK_MAIL_FROM"]
    # Claim outside the SMTP operation, so booking writes can still proceed.
    for _ in range(50):
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT * FROM mail_queue WHERE available<=? ORDER BY id LIMIT 1",(time.time(),)).fetchone()
        if not row:
            db.commit()
            return
        lease=secrets.token_hex(16)
        db.execute("UPDATE mail_queue SET available=?, lease=? WHERE id=?",(time.time()+300,lease,row["id"]))
        db.commit()
        try:
            msg=EmailMessage()
            msg["From"],msg["To"],msg["Subject"]=sender,row["recipient"],row["subject"]
            msg.set_content(row["body"])
            with smtplib.SMTP(host,int(os.getenv("BLENDBOOK_SMTP_PORT","587")),timeout=15) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if os.getenv("BLENDBOOK_SMTP_USER"):
                    smtp.login(os.environ["BLENDBOOK_SMTP_USER"],os.environ["BLENDBOOK_SMTP_PASSWORD"])
                smtp.send_message(msg)
            db.execute("DELETE FROM mail_queue WHERE id=? AND lease=?",(row["id"],lease))
        except (OSError,smtplib.SMTPException):
            db.execute("UPDATE mail_queue SET attempts=attempts+1, available=? WHERE id=? AND lease=?",
                       (time.time()+min(86400,60*2**min(row["attempts"],10)),row["id"],lease))
            db.commit()
            raise
        db.commit()

def calendar_event(b):
    midnight=datetime.fromisoformat(b["day"]).replace(tzinfo=ZoneInfo("Europe/Amsterdam"))
    def utc(t):
        return t.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    def escape(value):
        return value.replace("\\","\\\\").replace("\r","").replace("\n","\\n").replace(",","\\,").replace(";","\\;")
    lines=["BEGIN:VEVENT",
           "UID:"+b["ref"]+"@blendbook","DTSTAMP:"+utc(datetime.now(timezone.utc)),
           "DTSTART:"+utc(midnight+timedelta(minutes=b["start"])),
           "DTEND:"+utc(midnight+timedelta(minutes=b["finish"])),
           "SUMMARY:"+escape(b["service"]),"DESCRIPTION:"+escape(b["label"]+" (Amsterdam time)"),
           "END:VEVENT"]
    folded=[]
    for line in lines:
        part=""
        for ch in line:
            if len((part+ch).encode())>75:
                folded.append(part)
                part=" "
            part+=ch
        folded.append(part)
    return folded

def calendar_export(bookings):
    lines=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Blendbook//Booking//NL","X-WR-CALNAME:Blendbook"]
    for booking in bookings:
        lines.extend(calendar_event(booking))
    return ("\r\n".join([*lines,"END:VCALENDAR",""])).encode()

def calendar_file(b):
    return calendar_export([b])
