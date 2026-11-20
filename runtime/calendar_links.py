"""Read provider-hosted iCalendar subscriptions without exposing their URLs."""
import math
import os
from datetime import datetime, time, timedelta
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener, Request
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Amsterdam")
HOSTS = {"google": {"calendar.google.com"},
         "microsoft": {"outlook.live.com","outlook.office365.com","outlook.office.com"}}

class CalendarLinkError(Exception):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):
        return None

def install(db):
    db.execute("CREATE TABLE IF NOT EXISTS calendar_links(shop TEXT,provider TEXT,url BLOB NOT NULL,PRIMARY KEY(shop,provider))")

def cipher():
    from cryptography.fernet import Fernet
    return Fernet(os.environ["BLENDBOOK_TOKEN_KEY"].encode())

def validate_url(provider,url):
    parts=urlsplit(url)
    if (parts.scheme!="https" or parts.hostname not in HOSTS.get(provider,()) or
        parts.username or parts.password or parts.port not in (None,443) or
        parts.fragment or not parts.path.lower().endswith(".ics") or len(url)>4096):
        raise CalendarLinkError("Paste the HTTPS link to the ICS file from this calendar provider.")
    return url

def load_calendar(url):
    from icalendar import Calendar
    with build_opener(NoRedirect).open(Request(url,headers={"Accept":"text/calendar"}),timeout=7) as response:
        raw=response.read(3000001)
    if len(raw)>3000000 or not raw.lstrip().startswith(b"BEGIN:VCALENDAR"):
        raise ValueError()
    calendar=Calendar.from_ical(raw)
    if calendar.walk("VFREEBUSY"):
        raise ValueError()
    return calendar

def busy(calendar,day):
    import recurring_ical_events
    start=datetime.combine(day,time.min,ZONE)
    end=start+timedelta(days=1)
    def local(value):
        if not isinstance(value,datetime):
            return datetime.combine(value,time.min,ZONE)
        return value.astimezone(ZONE) if value.tzinfo else value.replace(tzinfo=ZONE)
    result=[]
    for event in recurring_ical_events.of(calendar).between(start,end):
        if str(event.get("STATUS","")).upper()=="CANCELLED" or str(event.get("TRANSP","")).upper()=="TRANSPARENT":
            continue
        left,right=local(event.start),local(event.end)
        if right>start and left<end:
            result.append((max(0,math.floor((left-start).total_seconds()/60)),min(1440,math.ceil((right-start).total_seconds()/60))))
    return result

def connect(db,shop,provider,url):
    url=validate_url(provider,url.strip())
    try:
        busy(load_calendar(url),datetime.now(ZONE).date())
        encrypted=cipher().encrypt(url.encode())
    except Exception as err:
        raise CalendarLinkError("Unable to read this calendar. Check the ICS link and sharing settings.") from err
    db.execute("INSERT OR REPLACE INTO calendar_links VALUES (?,?,?)",(shop,provider,encrypted))

def times(db,shop,day):
    result=[]
    try:
        for provider,encrypted in db.execute("SELECT provider,url FROM calendar_links WHERE shop=?",(shop,)):
            url=validate_url(provider,cipher().decrypt(encrypted).decode())
            result.extend(busy(load_calendar(url),day))
    except Exception as err:
        raise CalendarLinkError("The connected calendar is temporarily unavailable. Please try again later.") from err
    return result
