"""Email-verified workspace creation and access recovery."""
import hashlib
import os
import re
import secrets
import time
from urllib.parse import urlsplit
from customer import digest

def install(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS verification_links(digest TEXT PRIMARY KEY);
      CREATE TABLE IF NOT EXISTS passwords(shop TEXT PRIMARY KEY,salt BLOB NOT NULL,verifier BLOB NOT NULL);
      CREATE TABLE IF NOT EXISTS members(shop TEXT PRIMARY KEY,email TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS signup_links(digest TEXT PRIMARY KEY,shop TEXT,email TEXT,expires REAL);
      CREATE TABLE IF NOT EXISTS mail_limits(bucket TEXT PRIMARY KEY,started REAL,count INTEGER);
    """)

def start(db, data, address, link_owner=False):
    base=os.getenv("BLENDBOOK_PUBLIC_URL","").rstrip("/")
    if not (urlsplit(base).scheme=="https" and os.getenv("BLENDBOOK_SMTP_HOST") and os.getenv("BLENDBOOK_MAIL_FROM")):
        return 503,{"error":"Registratie opent zodra e-mail en het publieke adres zijn ingesteld."}
    email=data["email"].strip().lower()
    shop=data["shop"].strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email) or len(email)>254 or not re.fullmatch("[a-z0-9-]{1,48}",shop):
        raise ValueError("Controleer bedrijfscode en e-mail.")
    now=time.time()
    db.execute("DELETE FROM signup_links WHERE expires<?",(now,))
    db.execute("DELETE FROM mail_limits WHERE started<?",(now-3600,))
    for bucket,limit in ((address,30),(email,3)):
        hashed=digest(bucket)
        db.execute("INSERT INTO mail_limits VALUES (?,?,1) ON CONFLICT(bucket) DO UPDATE SET count=count+1",(hashed,now))
        count=db.execute("SELECT count FROM mail_limits WHERE bucket=?",(hashed,)).fetchone()[0]
        if count>limit:
            db.commit()
            return 429,{"error":"Probeer het over een uur opnieuw."}
    existing=db.execute("SELECT m.email FROM shops s LEFT JOIN members m ON m.shop=s.slug WHERE s.slug=?",(shop,)).fetchone()
    if existing is None or existing[0]==email or (link_owner and existing[0] is None):
        key=secrets.token_urlsafe(32)
        if link_owner:
            db.execute("INSERT INTO verification_links VALUES (?)",(digest(key),))
        db.execute("INSERT INTO signup_links VALUES (?,?,?,?)",(digest(key),shop,email,now+900))
        db.execute("INSERT INTO mail_queue(recipient,subject,body) VALUES (?,?,?)",
                   (email,"Open je Blendbook-werkruimte","Deze link is 15 minuten geldig.\n"+base+"/aanmelden#"+key))
    db.commit()
    return 202,{"message":"Als de bedrijfscode beschikbaar is of bij dit e-mailadres hoort, ontvang je een toegangslink."}

def finish(db,data,config):
    import json
    row=db.execute("SELECT * FROM signup_links WHERE digest=? AND expires>?",(digest(data["key"]),time.time())).fetchone()
    if not row:
        return 410,{"error":"De toegangslink is verlopen of gebruikt."}
    shop,email=row["shop"],row["email"]
    existing=db.execute("SELECT m.email FROM shops s LEFT JOIN members m ON m.shop=s.slug WHERE s.slug=?",(shop,)).fetchone()
    linking=db.execute("SELECT 1 FROM verification_links WHERE digest=?",(row["digest"],)).fetchone()
    if existing is not None and existing[0]!=email and not (linking and existing[0] is None):
        return 409,{"error":"Deze bedrijfscode is al in gebruik."}
    key=secrets.token_urlsafe(32)
    if existing is None:
        db.execute("INSERT INTO shops VALUES (?,?,?)",(shop,digest(key),json.dumps(config)))
        db.execute("INSERT INTO members VALUES (?,?)",(shop,email))
        db.execute("INSERT INTO design_owners VALUES (?,?)",(shop,"email:"+digest(email)))
    else:
        if linking and existing[0] is None:
            db.execute("INSERT INTO members VALUES (?,?)",(shop,email))
            db.execute("UPDATE design_owners SET owner=? WHERE shop=?",("email:"+digest(email),shop))
        db.execute("UPDATE shops SET secret=? WHERE slug=?",(digest(key),shop))
    db.execute("DELETE FROM verification_links WHERE digest IN (SELECT digest FROM signup_links WHERE shop=?)",(shop,))
    db.execute("DELETE FROM signup_links WHERE shop=?",(shop,))
    db.commit()
    return 200,{"shop":shop,"key":key}

def password_access(db, data, address, create, config):
    import json
    import hmac
    shop=data["shop"].strip()
    password=data["password"]
    if not re.fullmatch("[a-z0-9-]{1,48}",shop) or not isinstance(password,str) or not 12<=len(password)<=160:
        raise ValueError()
    now=time.time()
    bucket=digest("password:"+address)
    db.execute("DELETE FROM mail_limits WHERE bucket=? AND started<?",(bucket,now-600))
    db.execute("INSERT INTO mail_limits VALUES (?,?,1) ON CONFLICT(bucket) DO UPDATE SET count=count+1",(bucket,now))
    if db.execute("SELECT count FROM mail_limits WHERE bucket=?",(bucket,)).fetchone()[0]>40:
        return 429,{"error":"Te veel pogingen. Probeer het over tien minuten opnieuw."}
    row=db.execute("SELECT salt,verifier FROM passwords WHERE shop=?",(shop,)).fetchone()
    salt=row[0] if row else secrets.token_bytes(16)
    verifier=hashlib.scrypt(password.encode(),salt=salt,n=32768,r=8,p=1,maxmem=64*1024*1024)
    token=secrets.token_urlsafe(32)
    if create:
        if db.execute("SELECT 1 FROM shops WHERE slug=?",(shop,)).fetchone():
            return 409,{"error":"Deze bedrijfscode is bezet."}
        db.execute("INSERT INTO shops VALUES (?,?,?)",(shop,digest(token),json.dumps(config)))
        db.execute("INSERT INTO passwords VALUES (?,?,?)",(shop,salt,verifier))
        db.execute("INSERT INTO design_owners VALUES (?,?)",(shop,shop))
    elif row and hmac.compare_digest(verifier,row[1]):
        db.execute("UPDATE shops SET secret=? WHERE slug=?",(digest(token),shop))
    else:
        return 403,{"error":"Controleer de bedrijfscode en het wachtwoord."}
    db.commit()
    return 200,{"key":token,"shop":shop}
