"""Site palette sampling, structured design generation and durable monthly quota."""
import http.client
import ipaddress
import json
import os
import re
import secrets
import socket
import ssl
import time
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

MAX_BYTES = 220_000
FONTS = ("inherit", "system-ui", "Georgia", "Verdana", "Arial")
FIELDS = ("name", "background", "foreground", "accent", "font")


class DesignError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def install(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS design_owners(shop TEXT PRIMARY KEY, owner TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS design_batches(owner TEXT, month TEXT, nonce TEXT,
        started REAL, site TEXT, variants TEXT, PRIMARY KEY(owner,month));
      CREATE TABLE IF NOT EXISTS published_design(shop TEXT PRIMARY KEY, theme TEXT);
    """)
    db.execute("INSERT OR IGNORE INTO design_owners SELECT slug,slug FROM shops")


def owner_for(db, shop):
    row = db.execute("SELECT owner FROM design_owners WHERE shop=?", (shop,)).fetchone()
    return row[0] if row else shop


def period():
    return datetime.now(ZoneInfo("Europe/Amsterdam")).strftime("%Y-%m")


def active(db, shop):
    row = db.execute("SELECT theme FROM published_design WHERE shop=?", (shop,)).fetchone()
    return json.loads(row[0]) if row else None


def state(db, shop):
    month = period()
    row = db.execute("SELECT * FROM design_batches WHERE owner=? AND month=?",
                     (owner_for(db, shop), month)).fetchone()
    return dict(month=month, site=row["site"] if row else "", batch=row["nonce"] if row else "",
                variants=json.loads(row["variants"]) if row and row["variants"] else [],
                pending=bool(row and not row["variants"] and row["started"] > time.time()-300),
                active=active(db, shop))


def select(db, shop, data):
    snapshot = state(db, shop)
    index = data.get("index")
    if snapshot["batch"] != data.get("batch") or type(index) != int or not 0 <= index < len(snapshot["variants"]):
        raise DesignError(409, "Haal je ontwerpvarianten opnieuw op.")
    db.execute("INSERT OR REPLACE INTO published_design VALUES (?,?)",
               (shop, json.dumps(snapshot["variants"][index])))
    db.commit()
    return state(db, shop)


class PageStyles(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.styles = [], []
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.in_style |= tag == "style"
        if attrs.get("style"):
            self.styles.append(attrs["style"])
        if tag == "link" and "stylesheet" in (attrs.get("rel") or "").lower().split() and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "meta" and attrs.get("name") == "theme-color" and attrs.get("content"):
            self.styles.append(attrs["content"])

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False

    def handle_data(self, data):
        if self.in_style:
            self.styles.append(data)


def read_site(url):
    # Connect directly to the validated address while verifying TLS for the hostname.
    for _ in range(4):
        u = urlsplit(url)
        if u.scheme != "https" or not u.hostname or u.username or u.password or u.port not in (443,None):
            raise ValueError("Voer een openbaar HTTPS-adres in.")
        host = u.hostname.encode("idna").decode()
        addresses = socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global or ipaddress.ip_address(a[4][0]).is_multicast for a in addresses):
            raise ValueError("Alleen openbare websites zijn toegestaan.")
        address = addresses[0]
        with socket.socket(*address[:3]) as sock:
            sock.settimeout(5)
            sock.connect(address[4])
            conn = http.client.HTTPSConnection(host, timeout=5)
            try:
                conn.sock = ssl.create_default_context().wrap_socket(sock,server_hostname=host)
                conn.request("GET",(u.path or "/")+("?"+u.query if u.query else ""),
                             headers={"User-Agent":"Blendbook/1.0","Accept-Encoding":"identity"})
                response = conn.getresponse()
                if response.status in (301,302,303,307,308) and response.getheader("Location"):
                    url = urljoin(url,response.getheader("Location"))
                    continue
                if response.status != 200:
                    raise ValueError("Website is onbereikbaar.")
                return url,response.read(MAX_BYTES).decode("utf-8","replace")
            finally:
                conn.close()
    raise ValueError("Te veel doorverwijzingen.")


def sample(url):
    page, html = read_site(url)
    parser = PageStyles()
    parser.feed(html)
    for link in dict.fromkeys(parser.links[:3]):
        try:
            parser.styles.append(read_site(urljoin(page,link))[1])
        except (OSError, ValueError, http.client.HTTPException):
            continue
    css = " ".join(parser.styles)
    colors = Counter(x.lower() for x in re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b",css))
    fonts = re.findall(r"font-family\s*:\s*([a-zA-Z ,'\x22-]{2,80})",css,re.I)
    return {"colors":[s for s,_ in colors.most_common(16)], "fonts":fonts[:12]}


def provider(tokens, key):
    prompt = ("Create exactly three distinct, legible booking widget palettes using these sampled colors and fonts. "
              "Return a JSON object with variants, an array of three objects with name (short Dutch label), "
              "background, foreground, accent (six-digit hex) and font (inherit, system-ui, Georgia, Verdana or Arial). "
              "Foreground must contrast with background. The host site's typography is preferred. "
              "Data: "+json.dumps(tokens))
    payload = {"model":os.getenv("BLENDBOOK_AI_MODEL","gpt-4o-mini"),
               "response_format":{"type":"json_object"},"messages":[{"role":"user","content":prompt}]}
    req = Request(os.getenv("BLENDBOOK_AI_BASE_URL","https://api.openai.com/v1").rstrip("/")+"/chat/completions", data=json.dumps(payload).encode(),
                  headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    with urlopen(req,timeout=35) as response:
        output = json.load(response)["choices"][0]["message"]["content"]
    return json.loads(output)["variants"]


def luminance(color):
    channels = [int(color[i:i+2],16)/255 for i in (1,3,5)]
    return sum(w*(v/12.92 if v<=0.04045 else ((v+.055)/1.055)**2.4)
               for w,v in zip((.2126,.7152,.0722),channels))


def checked(items):
    if not isinstance(items,list) or len(items)!=3:
        raise ValueError("Drie varianten vereist.")
    result = [manual(item) for item in items]
    if len({tuple(t[k] for k in FIELDS[1:]) for t in result})!=3:
        raise ValueError("Varianten zijn identiek.")
    return result


def generate(db, shop, url):
    key = os.getenv("BLENDBOOK_AI_KEY")
    if not key:
        raise DesignError(503,"De platformbeheerder moet de AI-sleutel instellen.")
    if not isinstance(url,str) or len(url)>2000:
        raise ValueError("Ongeldig websiteadres.")
    owner, month, nonce = owner_for(db,shop),period(),secrets.token_hex(16)
    db.execute("BEGIN IMMEDIATE")
    snap = state(db,shop)
    if snap["variants"] or snap["pending"]:
        db.rollback()
        raise DesignError(409,"Deze maand is al een ontwerpserie gestart. Open de bestaande varianten.")
    db.execute("INSERT OR REPLACE INTO design_batches VALUES (?,?,?,?,?,NULL)",
               (owner,month,nonce,time.time(),url))
    db.commit()
    try:
        styles=sample(url)
        if not any(styles.values()):
            raise DesignError(422,"Geen kleuren of lettertypen gevonden op deze website.")
        themes=checked(provider(styles,key))
        updated=db.execute("UPDATE design_batches SET variants=? WHERE owner=? AND month=? AND nonce=?",
                           (json.dumps(themes),owner,month,nonce))
        db.commit()
        if updated.rowcount!=1:
            raise DesignError(409,"Open de nieuwste ontwerpserie.")
    except Exception as err:
        db.execute("DELETE FROM design_batches WHERE owner=? AND month=? AND nonce=? AND variants IS NULL",
                   (owner,month,nonce))
        db.commit()
        if isinstance(err,DesignError):
            raise
        raise DesignError(502,"Website of AI-provider leverde geen bruikbare ontwerpen. Probeer opnieuw.") from err
    return state(db,shop)


def manual(item):
    theme = {k:item[k] for k in FIELDS}
    if not isinstance(theme["name"],str) or not 1<=len(theme["name"])<=60 or theme["font"] not in FONTS:
        raise ValueError("Ongeldig ontwerp.")
    for k in ("background","foreground","accent"):
        if not re.fullmatch(r"#[a-fA-F0-9]{6}",theme[k]):
            raise ValueError("Ongeldige kleur.")
        theme[k]=theme[k].lower()
    bg,fg = sorted((luminance(theme["background"]),luminance(theme["foreground"])))
    if (fg+.05)/(bg+.05)<4.5:
        raise ValueError("Onvoldoende tekstcontrast.")
    theme["buttonText"] = "#000000" if luminance(theme["accent"])>.179 else "#ffffff"
    return theme
