import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
import app
import design
import calendars
from cryptography.fernet import Fernet

VARIANTS=[dict(name=n,background='#ffffff',foreground='#111111',accent=c,font='inherit')
          for n,c in [('Rust','#223344'),('Licht','#997733'),('Fris','#006655')]]

class Pilot(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        app.DB=self.tmp.name+'/state.db'
        self.env=patch.dict(os.environ,{'BLENDBOOK_AI_KEY':'test','BLENDBOOK_TOKEN_KEY':Fernet.generate_key().decode(),
             'BLENDBOOK_GOOGLE_ID':'test','BLENDBOOK_GOOGLE_SECRET':'test','BLENDBOOK_MICROSOFT_ID':'test',
             'BLENDBOOK_MICROSOFT_SECRET':'test','BLENDBOOK_SMTP_HOST':'fixture','BLENDBOOK_MAIL_FROM':'test@example.org',
             'BLENDBOOK_PUBLIC_URL':'https://example.org'})
        self.env.start()
        app.init()
        with app.connect() as db:
            for slug in ['studio','studio2']:
                db.execute("INSERT INTO shops VALUES (?,?,?)",(slug,hashlib.sha256(b'test').hexdigest(),json.dumps(app.DEFAULT)))
                db.execute("INSERT INTO design_owners VALUES (?,?)",(slug,'owner'))
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        d=datetime.now(app.ZONE).date()+timedelta(days=1)
        while d.weekday()>4:d+=timedelta(days=1)
        self.day=str(d)

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.env.stop()
        self.tmp.cleanup()

    def send(self,path,data=None,auth=True):
        headers={'Content-Type':'application/json'}
        if auth:headers['Authorization']='Bearer test'
        try:
            res=urlopen(Request(self.url+path,headers=headers,data=None if data is None else json.dumps(data).encode()))
        except HTTPError as err:
            res=err
        with res:
            raw=res.read()
            return res.status,json.loads(raw) if res.headers.get_content_type()=='application/json' else raw

    def test_design(self):
        path='/api/studio/generate'
        with patch.object(design,'sample',return_value={'colors':['#123456']}),patch.object(design,'provider',return_value=VARIANTS) as provider:
            with patch.object(design,'checked',side_effect=ValueError()):
                self.assertEqual(self.send(path,{'site':'https://example.org'})[0],502)
            provider.reset_mock()
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                results=list(pool.map(lambda slug:self.send('/api/'+slug+'/generate',{'site':'https://example.org'}),['studio','studio2']))
            self.assertEqual(sorted(r[0] for r in results),[201,409])
            self.assertEqual(provider.call_count,1)
            s=self.send('/api/studio/design')[1]
            self.assertEqual(len(s['variants']),3)
            self.assertEqual(self.send('/api/studio/publish',dict(batch=s['batch'],index=1))[0],200)
            self.assertEqual(self.send('/api/studio/config')[1]['theme']['name'],'Licht')
            self.assertIsNone(self.send('/api/studio2/config')[1]['theme'])
            with patch.object(design,'period',return_value='2099-03'):
                self.assertEqual(self.send(path,{'site':'https://example.org'})[0],201)
        with self.assertRaises(ValueError):design.read_site('https://127.0.0.1')

    def test_subscription(self):
        api='/api/studio/'
        self.assertEqual(self.send(api+'feed',{'enabled':True},auth=False)[0],403)
        path=self.send(api+'feed',{'enabled':True})[1]['path']
        b=self.send(api+'book',dict(day=self.day,start=480,name='Demo',email='demo@example.org'))[1]
        keys=dict(ref=b['reference'],key=b['manageKey'])
        initial=self.send(path,auth=False)[1]
        self.assertIn(b['reference'].encode(),initial)
        self.assertNotIn(b'demo@example.org',initial)
        self.send(api+'move',{**keys,'day':self.day,'start':600})
        self.assertIn('10:00–12:00'.encode(),self.send(path,auth=False)[1])
        self.send(api+'cancel',keys)
        self.assertNotIn(b'BEGIN:VEVENT',self.send(path,auth=False)[1])
        new=self.send(api+'feed',{'enabled':True})[1]['path']
        self.assertEqual(self.send(path,auth=False)[0],404)
        self.send(api+'feed',{'enabled':False})
        self.assertEqual(self.send(new,auth=False)[0],404)

    def test_customer(self):
        p='/api/studio/'
        data=dict(day=self.day,start=480,name='Demo',email='demo@example.org')
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:self.send(p+'book',data),range(2)))
        self.assertEqual(sorted(r[0] for r in results),[201,409])
        b=next(r[1] for r in results if r[0]==201)
        keys=dict(ref=b['reference'],key=b['manageKey'])
        self.assertEqual(self.send(p+'customer',{**keys,'key':'wrong'})[0],404)
        self.assertEqual(self.send(p+'move',{**keys,'day':self.day,'start':481})[0],409)
        self.assertEqual(self.send(p+'customer',keys)[1]['label'],'08:00–10:00')
        self.assertEqual(self.send(p+'move',{**keys,'day':self.day,'start':600})[1]['label'],'10:00–12:00')
        self.assertIn(b'BEGIN:VEVENT',self.send(p+'calendar',keys)[1])
        self.assertEqual(self.send(p+'cancel',keys)[0],200)
        self.assertEqual(self.send(p+'customer',keys)[0],404)
        with app.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM mail_queue').fetchone()[0],3)

    def test_calendar_adapters(self):
        for name in calendars.PROVIDERS:
            settings=calendars.settings(name)
            with app.connect() as db:
                db.execute("INSERT INTO calendars VALUES (?,?,?)",('studio',name,settings[3].encrypt(b'refresh')))
            interval=[self.day+'T08:00:00+01:00',self.day+'T09:00:00+01:00']
            response=({'calendars':{'primary':{'busy':[dict(zip(('start','end'),interval))]}}} if name=='google'
                      else {'value':[dict(start={'dateTime':interval[0]},end={'dateTime':interval[1]},showAs='busy')]})
            with patch.object(calendars,'request',side_effect=[{'access_token':'test'},response]):
                options=self.send('/api/studio/slots?day='+self.day)[1]
                self.assertFalse(any(s['start']==480 for s in options))
            with patch.object(calendars,'request',side_effect=calendars.CalendarError("offline")):
                self.assertEqual(self.send('/api/studio/slots?day='+self.day)[0],503)
            self.send('/api/studio/disconnect',{'provider':name})

    def test_signup(self):
        self.assertEqual(self.send('/api/account/start',{'email':'demo@example.org','shop':'new-shop'})[0],202)
        with app.connect() as db:
            key=db.execute('SELECT body FROM mail_queue').fetchone()[0].split('#')[-1]
        result=self.send('/api/account/finish',{'key':key})
        self.assertEqual(result[1]['shop'],'new-shop')
        self.assertEqual(self.send('/api/account/finish',{'key':key})[0],410)
