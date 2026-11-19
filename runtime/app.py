"""Blendbook booking server. Run with Python 3.10+."""
import calendars
import signup
import customer
import design
import argparse
import hashlib
import json
import os
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
DB = os.getenv("BLENDBOOK_DB", "blendbook.sqlite3")
ZONE = ZoneInfo("Europe/Amsterdam")
DEFAULT = dict(showServices=True, windows=True, duration=30, buffer=0,
               services=[dict(name="Kennismaking", duration=30, price="Gratis")],
               overrides={}, mailText="", hours=["08:00-17:00"] * 5 + ["", ""], closed=[], windowSize=120)

def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    return db

def init():
    with closing(connect()) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS shops(slug TEXT PRIMARY KEY, secret TEXT, config TEXT);
        CREATE TABLE IF NOT EXISTS bookings(ref TEXT PRIMARY KEY, shop TEXT, day TEXT,
          start INTEGER, finish INTEGER, occupied_start INTEGER, occupied_end INTEGER,
          service TEXT, price TEXT, name TEXT, email TEXT, label TEXT);
        CREATE INDEX IF NOT EXISTS calendar ON bookings(shop,day);
        """)
        design.install(db)
        customer.install(db)
        signup.install(db)
        calendars.install(db)
        db.commit()

def minutes(t):
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t):
        raise ValueError("Gebruik tijden als 08:00.")
    h, m = map(int, t.split(":"))
    return h*60+m

def interval(value):
    start, end = map(minutes, value.split("-"))
    if end <= start:
        raise ValueError("De eindtijd moet later zijn.")
    return start, end

def number(n, low, high):
    if type(n) is not int or not low <= n <= high:
        raise ValueError("Controleer de ingestelde minuten.")
    return n

def validate(c):
    for key in ("windows", "showServices"):
        if type(c[key]) is not bool:
            raise ValueError("Ongeldige instelling.")
    number(c["duration"], 5, 720)
    number(c["buffer"], 0, 180)
    number(c["windowSize"], 15, 720)
    if len(c["hours"]) != 7:
        raise ValueError("Geef zeven weekdagen op.")
    c.setdefault("overrides", {})
    c.setdefault("mailText", "")
    if not isinstance(c["mailText"],str) or len(c["mailText"])>2000 or len(c["overrides"])>366:
        raise ValueError()
    for day in c["overrides"]:
        date.fromisoformat(day)
    for h in filter(None, [*c["hours"], *c["overrides"].values()]):
        blocks = [interval(part.strip()) for part in h.split(",")]
        if any(current[0] < previous[1] for previous,current in zip(blocks,blocks[1:])):
            raise ValueError("Tijdblokken overlappen of staan in de verkeerde volgorde.")
    for day in c["closed"]:
        date.fromisoformat(day)
    if len(c["services"]) > 80 or (c["showServices"] and not c["services"]):
        raise ValueError("Controleer je dienstenlijst.")
    for s in c["services"]:
        number(s["duration"], 5, 720)
        if not str(s["name"]).strip() or not isinstance(s["price"], str):
            raise ValueError("Controleer de dienstnaam en prijs.")
    return {k:c[k] for k in DEFAULT}

def clock(m):
    return f"{m//60:02}:{m%60:02}"

def slots(db, shop, c, day, index, external=()):
    now = datetime.now(ZONE)
    d = date.fromisoformat(day)
    if d < now.date() or d > now.date()+timedelta(days=365) or day in c["closed"]:
        return []
    hours = c.get("overrides",{}).get(day,c["hours"][d.weekday()])
    if not hours:
        return []
    service = dict(name="Afspraak", duration=c["duration"], price="")
    if c["showServices"]:
        if not 0 <= index < len(c["services"]):
            raise ValueError("Kies een dienst.")
        service = c["services"][index]
    busy = db.execute("SELECT occupied_start, occupied_end FROM bookings WHERE shop=? AND day=?", (shop,day)).fetchall()
    busy.extend(external)
    output = []
    step = c["windowSize"] if c["windows"] else 15
    for block in hours.split(","):
        opening,end=interval(block.strip())
        for start in range(opening, end, step):
            arrival_end = start + step if c["windows"] else start
            finish = arrival_end + service["duration"]
            # Keep the service duration available even for the latest promised arrival.
            if finish > end or (d == now.date() and start <= now.hour*60+now.minute):
                continue
            a, b = start-c["buffer"], finish+c["buffer"]
            if a < opening or b > end or any(a < right and b > left for left,right in busy):
                continue
            label = clock(start) + ("–"+clock(arrival_end) if c["windows"] else "")
            output.append(dict(start=start, finish=finish, occupied_start=a, occupied_end=b,
                               label=label, service=service["name"], price=service["price"]))
    return output

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body, mime="application/json"):
        payload = json.dumps(body, ensure_ascii=False).encode() if mime=="application/json" else body
        self.send_response(status)
        self.send_header("Content-Type", mime+"; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.end_headers()

    def do_GET(self):
        self.handle_request(False)

    def do_POST(self):
        self.handle_request(True)

    def handle_request(self, post):
        u = urlsplit(self.path)
        if not post and u.path=="/oauth/callback":
            try:
                with closing(connect()) as db,db:
                    calendars.finish(db,parse_qs(u.query))
                return self.reply(200,b'Agenda gekoppeld. <a href="/admin">Terug naar het dashboard</a>',"text/html")
            except (calendars.CalendarError,KeyError,ValueError):
                return self.reply(400,{"error":"Koppeling niet afgerond. Probeer opnieuw vanuit het dashboard."})
        feed=re.fullmatch(r"/agenda/([a-z0-9-]{1,48})/([A-Za-z0-9_-]{43})\.ics",u.path)
        if not post and feed:
            shop,key=feed.groups()
            with closing(connect()) as db:
                row=db.execute("SELECT digest FROM calendar_feeds WHERE shop=?",(shop,)).fetchone()
                if not row or not secrets.compare_digest(row[0],customer.digest(key)):
                    return self.reply(404,{"error":"Agendalink ongeldig."})
                bookings=db.execute("SELECT * FROM bookings WHERE shop=? ORDER BY day,start",(shop,))
                return self.reply(200,customer.calendar_export(bookings),"text/calendar")
        files={"/":"book.html" if "bedrijf" in parse_qs(u.query) else "home.html","/boeken":"book.html","/ui.css":"ui.css","/dashboard.js":"dashboard.js","/home.js":"home.js","/admin":"admin.html","/aanmelden":"signup.html","/beheer-afspraak":"manage.html","/design.js":"design.js","/widget.js":"widget.js"}
        if not post and u.path in files:
            return self.reply(200,(HERE/files[u.path]).read_bytes(),"text/javascript" if u.path.endswith(".js") else "text/css" if u.path.endswith(".css") else "text/html")
        match = re.fullmatch(r"/api/([a-z0-9-]{1,48})/(config|slots|book|admin|design|generate|publish|customer|cancel|calendar|move|connect|disconnect|feed|theme|managecancel|managemove|verify)",u.path)
        account = re.fullmatch(r"/api/account/(start|finish|register|login)",u.path) if post else None
        if not match and not account:
            return self.reply(404,{"error":"Onbekende pagina."})
        shop, action = match.groups() if match else ("",account[1])
        try:
            data={}
            if post:
                size=int(self.headers.get("Content-Length","0"))
                if not 0<size<=32768 or self.headers.get_content_type()!="application/json":
                    return self.reply(400,{"error":"Ongeldige aanvraag."})
                data=json.loads(self.rfile.read(size))
            with closing(connect()) as db, db:
                external=[]
                if action in ("book","move","slots"):
                    day=data.get("day") if post else parse_qs(u.query).get("day",[""])[0]
                    external=calendars.times(db,shop,day)
                if post and action not in ("generate","managemove"):
                    db.execute("BEGIN IMMEDIATE")
                if account:
                    if action in ("register","login"):
                        return self.reply(*signup.password_access(db,data,self.client_address[0],action=="register",DEFAULT))
                    result=signup.start(db,data,self.client_address[0]) if action=="start" else signup.finish(db,data,DEFAULT)
                    return self.reply(*result)
                row=db.execute("SELECT * FROM shops WHERE slug=?",(shop,)).fetchone()
                if not row:
                    return self.reply(404,{"error":"Onbekend bedrijf."})
                c={**DEFAULT,**json.loads(row["config"])}
                staff_change=action in ("managecancel","managemove")
                if action in ("verify","theme","managecancel","managemove","admin","design","generate","publish","connect","disconnect","feed"):
                    token=self.headers.get("Authorization","").removeprefix("Bearer ")
                    if not secrets.compare_digest(hashlib.sha256(token.encode()).hexdigest(),row["secret"]):
                        return self.reply(403,{"error":"Controleer de beheersleutel."})
                    if action=="verify" and post:
                        return self.reply(*signup.start(db,{"shop":shop,"email":data["email"]},self.client_address[0],True))
                    if staff_change and post:
                        if action=="managemove":
                            external=calendars.times(db,shop,data["day"])
                            db.execute("BEGIN IMMEDIATE")
                            c={**DEFAULT,**json.loads(db.execute("SELECT config FROM shops WHERE slug=?",(shop,)).fetchone()[0])}
                        action="move" if action=="managemove" else "cancel"
                    if post and action=="theme":
                        theme=design.manual(data)
                        db.execute("INSERT OR REPLACE INTO published_design VALUES (?,?)",(shop,json.dumps(theme)))
                        db.commit()
                        return self.reply(200,theme)
                    if post and action=="feed":
                        db.execute("DELETE FROM calendar_feeds WHERE shop=?",(shop,))
                        path=None
                        if data.get("enabled") is True:
                            key=secrets.token_urlsafe(32)
                            db.execute("INSERT INTO calendar_feeds VALUES (?,?)",(shop,customer.digest(key)))
                            path=f"/agenda/{shop}/{key}.ics"
                        db.commit()
                        return self.reply(200,{"path":path})
                    if action=="connect" and post:
                        return self.reply(200,{"url":calendars.begin(db,shop,data["provider"])})
                    if action=="disconnect" and post:
                        db.execute("DELETE FROM calendars WHERE shop=? AND provider=?",(shop,data["provider"]))
                        db.execute("DELETE FROM oauth_states WHERE shop=? AND provider=?",(shop,data["provider"]))
                        db.commit()
                        return self.reply(200,{"removed":True})
                    if action=="design" and not post:
                        return self.reply(200,design.state(db,shop))
                    if action=="generate" and post:
                        if db.execute("SELECT 1 FROM passwords WHERE shop=?",(shop,)).fetchone() and not db.execute("SELECT 1 FROM members WHERE shop=?",(shop,)).fetchone():
                            return self.reply(403,{"error":"Verifieer eerst je e-mailadres voor de maandelijkse AI-generatie."})
                        return self.reply(201,design.generate(db,shop,data["site"]))
                    if action=="publish" and post:
                        return self.reply(200,design.select(db,shop,data))
                    if not staff_change:
                        if action!="admin":
                            return self.reply(405,{"error":"Ongeldige methode."})
                        if post:
                            c=validate(data)
                            db.execute("UPDATE shops SET config=? WHERE slug=?",(json.dumps(c),shop))
                            db.commit()
                        reservations=[dict(b) for b in db.execute("SELECT day,label,service,price,name,email,ref FROM bookings WHERE shop=? ORDER BY day,start",(shop,))]
                        return self.reply(200,dict(config=c,theme=design.active(db,shop),ready={key:all(os.getenv("BLENDBOOK_"+v) for v in variables) for key,variables in {"smtp":["SMTP_HOST","MAIL_FROM"],"google":["GOOGLE_ID","GOOGLE_SECRET","TOKEN_KEY","PUBLIC_URL"],"microsoft":["MICROSOFT_ID","MICROSOFT_SECRET","TOKEN_KEY","PUBLIC_URL"],"ai":["AI_KEY"]}.items()},bookings=reservations,calendars=[r[0] for r in db.execute("SELECT provider FROM calendars WHERE shop=?",(shop,))]))
                if not post and action=="config":
                    return self.reply(200,dict(theme=design.active(db,shop), **{k:c[k] for k in ("showServices","services","windows","duration")}))
                if not post and action=="slots":
                    q=parse_qs(u.query)
                    return self.reply(200,slots(db,shop,c,q["day"][0],int(q.get("service",[0])[0]),external))
                if post and action=="book":
                    name=data["name"].strip()
                    email=data["email"].strip()
                    if not 0<len(name)<=120 or len(email)>254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email):
                        raise ValueError("Vul je naam en e-mailadres in.")
                    options=slots(db,shop,c,data["day"],int(data.get("service",0)),external)
                    chosen=next((s for s in options if s["start"]==data["start"]),None)
                    if not chosen:
                        return self.reply(409,{"error":"Deze tijd is niet meer beschikbaar."})
                    ref=secrets.token_hex(8)
                    db.execute("INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (ref,shop,data["day"],chosen["start"],chosen["finish"],chosen["occupied_start"],chosen["occupied_end"],chosen["service"],chosen["price"],name,email,chosen["label"]))
                    key=customer.new_key(db,ref)
                    booked=customer.lookup(db,shop,ref,key)
                    customer.notice(db,booked,"Afspraak bevestigd",key)
                    db.commit()
                    return self.reply(201,dict(manageKey=key,reference=ref,day=data["day"],label=chosen["label"],service=chosen["service"]))
                if post and action in ("customer","cancel","calendar","move"):
                    b=(db.execute("SELECT * FROM bookings WHERE shop=? AND ref=?",(shop,data["ref"])).fetchone() if staff_change else customer.lookup(db,shop,data["ref"],data["key"]))
                    if not b:
                        return self.reply(404,{"error":"Deze beheerlink is ongeldig of de afspraak is geannuleerd."})
                    if action=="calendar":
                        return self.reply(200,customer.calendar_file(b),"text/calendar")
                    if action=="cancel":
                        customer.notice(db,b,"Afspraak geannuleerd")
                        db.execute("DELETE FROM bookings WHERE ref=?",(b["ref"],))
                        db.execute("DELETE FROM customer_keys WHERE ref=?",(b["ref"],))
                        db.commit()
                        return self.reply(200,{"cancelled":True})
                    if action=="move":
                        # Remove the original inside this transaction. A conflict rolls it back.
                        if c["showServices"]:
                            index=next((i for i,s in enumerate(c["services"]) if s["name"]==b["service"]),None)
                            if index is None:
                                return self.reply(409,{"error":"Deze dienst is gewijzigd. Neem contact op met het bedrijf."})
                        else:
                            index=0
                        db.execute("DELETE FROM bookings WHERE ref=?",(b["ref"],))
                        option=next((s for s in slots(db,shop,c,data["day"],index,external) if s["start"]==data["start"]),None)
                        if not option:
                            db.rollback()
                            return self.reply(409,{"error":"Deze tijd is niet beschikbaar."})
                        db.execute("INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (b["ref"],shop,data["day"],option["start"],option["finish"],option["occupied_start"],
                             option["occupied_end"],b["service"],b["price"],b["name"],b["email"],option["label"]))
                        b=(db.execute("SELECT * FROM bookings WHERE shop=? AND ref=?",(shop,data["ref"])).fetchone() if staff_change else customer.lookup(db,shop,data["ref"],data["key"]))
                        customer.notice(db,b,"Afspraak verplaatst",data.get("key") if not staff_change else None)
                        db.commit()
                    return self.reply(200,{k:b[k] for k in ("ref","day","label","service","price")})
                self.reply(405,{"error":"Ongeldige methode."})
        except calendars.CalendarError as err:
            self.reply(503,{"error":str(err)})
        except design.DesignError as err:
            self.reply(err.status,{"error":str(err)})
        except (ValueError,KeyError,TypeError,AttributeError,IndexError):
            self.reply(400,{"error":"Controleer de ingevulde gegevens."})

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--create",metavar="BEDRIJF")
    parser.add_argument("--port",type=int,default=8787)
    parser.add_argument("--owner",help="Gedeelde gebruikers-ID voor de maandlimiet")
    parser.add_argument("--deliver-mail",action="store_true")
    args=parser.parse_args()
    init()
    if args.deliver_mail:
        with closing(connect()) as db:
            customer.deliver(db)
    elif args.create:
        if not re.fullmatch("[a-z0-9-]{1,48}",args.create):
            parser.error("Gebruik kleine letters, cijfers en streepjes.")
        token=secrets.token_urlsafe(32)
        with closing(connect()) as db, db:
            db.execute("INSERT INTO shops VALUES (?,?,?)",(args.create,hashlib.sha256(token.encode()).hexdigest(),json.dumps(DEFAULT)))
            db.execute("INSERT INTO design_owners VALUES (?,?)",(args.create,args.owner or args.create))
        print("Beheersleutel:",token)
    else:
        ThreadingHTTPServer(("127.0.0.1",args.port),Handler).serve_forever()
