"""Local prototype API. Not production-hardened; deploy only after security review."""
import json, os, re, sqlite3, secrets, threading
from security import allowed, notify
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
DB=Path(os.getenv('RM_DB',str(ROOT/'renovationmatch.sqlite3')))
TOKEN=os.getenv('RM_ADMIN_TOKEN','')

def connect():
    db=sqlite3.connect(DB,timeout=15)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA busy_timeout=15000')
    return db

def init():
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY, project_type TEXT NOT NULL, city TEXT NOT NULL, budget TEXT, timing TEXT, details TEXT NOT NULL, name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL, consent INTEGER NOT NULL, created_at TEXT NOT NULL, assigned_contractor INTEGER UNIQUE, status TEXT NOT NULL DEFAULT "new")')
        db.execute('CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, event TEXT NOT NULL, subject_id INTEGER, created_at TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS contractors (id INTEGER PRIMARY KEY, business TEXT NOT NULL, contact TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL, services TEXT NOT NULL, cities TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT "pending")')
        # One lead may be assigned only once; a contractor may receive many leads.
        db.execute('DROP INDEX IF EXISTS ix_lead_contractor_unique')
        db.execute('CREATE INDEX IF NOT EXISTS ix_lead_status ON leads(status)')
        # Migration for initial prototype schema: remove accidental uniqueness on contractor
        cols=db.execute('PRAGMA index_list(leads)').fetchall()
        for idx in cols:
            if idx['origin']=='u':
                db.execute('ALTER TABLE leads RENAME TO leads_old')
                db.execute('CREATE TABLE leads (id INTEGER PRIMARY KEY, project_type TEXT NOT NULL, city TEXT NOT NULL, budget TEXT, timing TEXT, details TEXT NOT NULL, name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL, consent INTEGER NOT NULL, created_at TEXT NOT NULL, assigned_contractor INTEGER, status TEXT NOT NULL DEFAULT "new")')
                db.execute('INSERT INTO leads SELECT * FROM leads_old')
                db.execute('DROP TABLE leads_old')
                break

def clean(v,limit=500): return str(v or '').strip()[:limit]
def valid_email(v): return bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v))
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def send_json(self,code,obj):
        body=json.dumps(obj).encode()
        self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def end_headers(self):
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'")
        super().end_headers()
    def admin(self): return bool(TOKEN) and secrets.compare_digest(self.headers.get('X-Admin-Token',''),TOKEN)
    def do_GET(self):
        path=urlparse(self.path).path
        if path in ('/server.py','/security.py','/README.md','/requirements.txt') or path.startswith('/.') or path.endswith(('.sqlite3','.sqlite3-wal','.sqlite3-shm','.db','.pyc')):return self.send_json(404,{'error':'Not found'})
        if path=='/api/health':return self.send_json(200,{'ok':True,'mode':'local-prototype'})
        if path=='/api/admin/leads':
            if not self.admin():return self.send_json(403,{'error':'Admin token required'})
            with connect() as db: rows=[dict(r) for r in db.execute('SELECT * FROM leads ORDER BY id DESC')]
            return self.send_json(200,{'leads':rows})
        if path=='/api/admin/contractors':
            if not self.admin():return self.send_json(403,{'error':'Admin token required'})
            with connect() as db: rows=[dict(r) for r in db.execute('SELECT * FROM contractors ORDER BY id DESC')]
            return self.send_json(200,{'contractors':rows})
        if path.startswith('/api/') or path.endswith('.sqlite3'):return self.send_json(404,{'error':'Not found'})
        return super().do_GET()
    def do_POST(self):
        path=urlparse(self.path).path
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n<=0 or n>16000: return self.send_json(413,{'error':'Invalid request size'})
            data=json.loads(self.rfile.read(n))
            if not isinstance(data,dict):raise ValueError()
        except (ValueError,TypeError,json.JSONDecodeError):return self.send_json(400,{'error':'Invalid JSON'})
        now=datetime.now(timezone.utc).isoformat()
        if path in ('/api/leads','/api/contractors') and not allowed((path,self.client_address[0])):return self.send_json(429,{'error':'Too many requests; please try later'})
        if path=='/api/leads':
            fields={k:clean(data.get(k),2000 if k=='details' else 150) for k in ('project_type','city','budget','timing','details','name','email','phone')}
            if any(not fields[k] for k in ('project_type','city','details','name','email','phone')) or not valid_email(fields['email']) or len(re.sub(r'\D','',fields['phone']))<10 or data.get('consent') is not True:return self.send_json(400,{'error':'Please complete required fields and consent'})
            with connect() as db:
                cur=db.execute('INSERT INTO leads(project_type,city,budget,timing,details,name,email,phone,consent,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',(*fields.values(),1,now))
            lead_id=cur.lastrowid
            with connect() as db:db.execute('INSERT INTO audit(event,subject_id,created_at) VALUES (?,?,?)',('lead_created',lead_id,now))
            threading.Thread(target=self._notify,args=('New renovation request',f'Lead #{lead_id} received. Open your admin dashboard to review.'),daemon=True).start()
            return self.send_json(201,{'ok':True,'request_id':lead_id})
        if path=='/api/contractors':
            fields={k:clean(data.get(k),500) for k in ('business','contact','email','phone','services','cities')}
            if any(not v for v in fields.values()) or not valid_email(fields['email']):return self.send_json(400,{'error':'All contractor fields are required'})
            with connect() as db:
                cur=db.execute('INSERT INTO contractors(business,contact,email,phone,services,cities,created_at) VALUES (?,?,?,?,?,?,?)',(*fields.values(),now))
            contractor_id=cur.lastrowid
            threading.Thread(target=self._notify,args=('New contractor application',f'Contractor #{contractor_id} registered. Review in admin dashboard.'),daemon=True).start()
            return self.send_json(201,{'ok':True,'contractor_id':contractor_id})
        if path=='/api/admin/assign':
            if not self.admin():return self.send_json(403,{'error':'Admin token required'})
            try:lead_id=int(data['lead_id']);contractor_id=int(data['contractor_id'])
            except (ValueError,TypeError,KeyError):return self.send_json(400,{'error':'Invalid IDs'})
            with connect() as db:
                if not db.execute('SELECT 1 FROM contractors WHERE id=?',(contractor_id,)).fetchone():return self.send_json(404,{'error':'Contractor not found'})
                cur=db.execute("UPDATE leads SET assigned_contractor=?,status='assigned' WHERE id=? AND assigned_contractor IS NULL AND status='new'",(contractor_id,lead_id))
                if not cur.rowcount:return self.send_json(409,{'error':'Lead not found or already assigned'})
            with connect() as db:db.execute('INSERT INTO audit(event,subject_id,created_at) VALUES (?,?,?)',('lead_assigned',lead_id,now))
            return self.send_json(200,{'ok':True})
        return self.send_json(404,{'error':'Not found'})
    @staticmethod
    def _notify(subject,message):
        try:notify(subject,message)
        except Exception as exc:print('Notification delivery failed:',type(exc).__name__)
if __name__=='__main__':
    init();port=int(os.getenv('PORT','8000'))
    print(f'Open http://127.0.0.1:{port} (local development only)')
    ThreadingHTTPServer((os.getenv('RM_HOST','127.0.0.1'),port),Handler).serve_forever()
