"""Read connected Google and Microsoft primary calendars before offering a slot."""
import hashlib
import json
import math
import os
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ZONE=ZoneInfo("Europe/Amsterdam")
PROVIDERS={
 "google":("https://accounts.google.com/o/oauth2/v2/auth","https://oauth2.googleapis.com/token","https://www.googleapis.com/auth/calendar.events.freebusy"),
 "microsoft":("https://login.microsoftonline.com/common/oauth2/v2.0/authorize","https://login.microsoftonline.com/common/oauth2/v2.0/token","offline_access Calendars.ReadBasic")
}

class CalendarError(Exception):
    pass

def install(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS oauth_states(state TEXT PRIMARY KEY,shop TEXT,provider TEXT,expires REAL,verifier TEXT);
      CREATE TABLE IF NOT EXISTS calendars(shop TEXT,provider TEXT,refresh BLOB,PRIMARY KEY(shop,provider));
    """)

def settings(name):
    if name not in PROVIDERS:
        raise ValueError("Onbekende agendaprovider.")
    prefix="BLENDBOOK_"+name.upper()+"_"
    try:
        from cryptography.fernet import Fernet
        cipher=Fernet(os.environ["BLENDBOOK_TOKEN_KEY"].encode())
        base=os.environ["BLENDBOOK_PUBLIC_URL"].rstrip("/")
        if not base.startswith("https://"): raise ValueError()
        return os.environ[prefix+"ID"],os.environ[prefix+"SECRET"],os.getenv("BLENDBOOK_OAUTH_CALLBACK") or base+"/oauth/callback",cipher
    except (ImportError,ValueError,KeyError) as err:
        raise CalendarError("De platformbeheerder moet de agendakoppeling configureren.") from err

def begin(db,shop,name):
    import base64
    client,_,redirect,_=settings(name)
    state,verifier=secrets.token_urlsafe(32),secrets.token_urlsafe(48)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    db.execute("DELETE FROM oauth_states WHERE expires<?",(time.time(),))
    db.execute("INSERT INTO oauth_states VALUES (?,?,?,?,?)",(state,shop,name,time.time()+600,verifier))
    db.commit()
    params=dict(client_id=client,redirect_uri=redirect,response_type="code",state=state,
                scope=PROVIDERS[name][2],code_challenge=challenge,code_challenge_method="S256")
    if name=="google":params.update(access_type="offline",prompt="consent")
    return PROVIDERS[name][0]+"?"+urlencode(params)

def request(url, data=None, headers=None):
    try:
        with urlopen(Request(url,data=data,headers=headers or {}),timeout=6) as response:
            return json.load(response)
    except Exception as err:
        raise CalendarError("Agenda tijdelijk onbereikbaar. Probeer opnieuw of verbind de agenda opnieuw.") from err

def token(name, **params):
    client,secret,_,_=settings(name)
    params.update(client_id=client,client_secret=secret)
    return request(PROVIDERS[name][1],urlencode(params).encode())

def finish(db,q):
    state=db.execute("SELECT * FROM oauth_states WHERE state=? AND expires>?",(q["state"][0],time.time())).fetchone()
    if not state:
        raise CalendarError("De koppelingslink is verlopen.")
    db.execute("DELETE FROM oauth_states WHERE state=?",(state["state"],))
    db.commit()
    name=state["provider"]
    _,_,redirect,cipher=settings(name)
    result=token(name,grant_type="authorization_code",code=q["code"][0],redirect_uri=redirect,code_verifier=state["verifier"])
    if not result.get("refresh_token"):
        raise CalendarError("Offline toegang ontbreekt. Verbind de agenda opnieuw.")
    db.execute("INSERT OR REPLACE INTO calendars VALUES (?,?,?)",(state["shop"],name,cipher.encrypt(result["refresh_token"].encode())))
    db.commit()

def times(db, shop, day):
    d=date.fromisoformat(day)
    start=datetime.combine(d,datetime.min.time(),ZONE)
    end=start+timedelta(days=1)
    if d<datetime.now(ZONE).date() or d>datetime.now(ZONE).date()+timedelta(days=365):return []
    result=[]
    rows=db.execute("SELECT provider,refresh FROM calendars WHERE shop=?",(shop,)).fetchall()
    for name,old in rows:
        _,_,_,cipher=settings(name)
        try:
            raw=cipher.decrypt(old).decode()
            access=token(name,grant_type="refresh_token",refresh_token=raw)
            if access.get("refresh_token") and access["refresh_token"]!=raw:
                db.execute("UPDATE calendars SET refresh=? WHERE shop=? AND provider=? AND refresh=?",(cipher.encrypt(access["refresh_token"].encode()),shop,name,old))
                db.commit()
            headers={"Authorization":"Bearer "+access["access_token"],"Content-Type":"application/json"}
            if name=="google":
                body=dict(timeMin=start.isoformat(),timeMax=end.isoformat(),items=[{"id":"primary"}])
                calendar=request("https://www.googleapis.com/calendar/v3/freeBusy",json.dumps(body).encode(),headers)["calendars"]["primary"]
                if calendar.get("errors"):raise ValueError()
                events=[(b["start"],b["end"]) for b in calendar["busy"]]
            else:
                query=urlencode({"startDateTime":start.isoformat(),"endDateTime":end.isoformat(),"$select":"start,end,showAs,isCancelled","$top":"100"})
                url="https://graph.microsoft.com/v1.0/me/calendarView?"+query
                events=[]
                for page in range(20):
                    data=request(url,headers=headers)
                    for b in data["value"]:
                        if b.get("isCancelled") or b["showAs"]=="free":continue
                        # Graph returns UTC by default when Prefer: outlook.timezone is omitted.
                        events.append(tuple(b[k]["dateTime"] for k in ("start","end")))
                    url=data.get("@odata.nextLink")
                    if not url:break
                    if not url.startswith("https://graph.microsoft.com/"):raise ValueError()
                else:raise ValueError()
            for left,right in events:
                def offset(value):
                    stamp=datetime.fromisoformat(value.replace("Z","+00:00"))
                    if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
                    return (stamp.astimezone(ZONE).replace(tzinfo=None)-start.replace(tzinfo=None)).total_seconds()/60
                result.append((math.floor(offset(left)),math.ceil(offset(right))))
        except Exception as err:
            raise CalendarError("Beschikbaarheid van de gekoppelde agenda kon niet worden bevestigd.") from err
    return result
