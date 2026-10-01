import os, re, sqlite3, secrets
from datetime import datetime, date
from pathlib import Path
import bcrypt
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

BASE=Path(__file__).resolve().parent.parent; DATA=BASE/'data'; UPLOADS=DATA/'uploads'; FRONT=BASE/'frontend'
DB=Path(os.getenv('DATABASE_PATH',str(DATA/'diary.db'))); UPLOADS.mkdir(parents=True,exist_ok=True); DB.parent.mkdir(parents=True,exist_ok=True)
SECRET=os.getenv('SECRET_KEY','dev-only-change-this-before-production'); MAX=8*1024*1024
ALLOWED={'image/jpeg','image/png','image/webp','image/gif'}
app=FastAPI(title='Private Diary')
app.add_middleware(SessionMiddleware,secret_key=SECRET,session_cookie='private_diary_session',same_site='lax',https_only=os.getenv('HTTPS_ONLY','false').lower()=='true',max_age=60*60*24*30)

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
 c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL UNIQUE COLLATE NOCASE,password_hash TEXT NOT NULL,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS entries(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,title TEXT NOT NULL,content TEXT NOT NULL,entry_date TEXT NOT NULL,mood INTEGER NOT NULL DEFAULT 4,theme TEXT NOT NULL DEFAULT 'auto',is_locked INTEGER NOT NULL DEFAULT 0,lock_hash TEXT,photo_path TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);CREATE INDEX IF NOT EXISTS idx_entries_user_date ON entries(user_id,entry_date);'''); return c
def now(): return datetime.now().isoformat(timespec='seconds')
def user(request):
 uid=request.session.get('user_id')
 if not uid:return None
 c=db(); r=c.execute('SELECT id,username,created_at FROM users WHERE id=?',(uid,)).fetchone(); c.close(); return r
def requser(request):
 u=user(request)
 if not u:raise HTTPException(401,'Please log in.')
 return u
def uname(v):
 v=v.strip()
 if not re.fullmatch(r'[A-Za-z0-9_.-]{3,24}',v):raise HTTPException(400,'Username must be 3–24 characters and use letters, numbers, _, ., or -.')
 return v
def validdate(v):
 try:date.fromisoformat(v)
 except:raise HTTPException(400,'Invalid date.')
def jsonify(r,locked=False):
 return {'id':r['id'],'title':r['title'],'content':None if locked else r['content'],'entry_date':r['entry_date'],'mood':r['mood'],'theme':r['theme'],'is_locked':bool(r['is_locked']),'photo_url':f"/api/uploads/{r['id']}" if r['photo_path'] else None,'created_at':r['created_at'],'updated_at':r['updated_at']}

@app.get('/api/me')
def me(request:Request):
 u=user(request); return {'authenticated':bool(u),**({'user':dict(u)} if u else {})}
@app.post('/api/auth/signup')
def signup(request:Request,username:str=Form(...),password:str=Form(...)):
 username=uname(username)
 if len(password)<8:raise HTTPException(400,'Password must be at least 8 characters.')
 c=db();
 if c.execute('SELECT id FROM users WHERE username=? COLLATE NOCASE',(username,)).fetchone():c.close();raise HTTPException(409,'That username is already taken.')
 cur=c.execute('INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)',(username,bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode(),now()));c.commit();uid=cur.lastrowid;c.close();request.session.clear();request.session['user_id']=uid
 return {'ok':True,'user':{'id':uid,'username':username}}
@app.post('/api/auth/login')
def login(request:Request,username:str=Form(...),password:str=Form(...)):
 c=db();r=c.execute('SELECT * FROM users WHERE username=? COLLATE NOCASE',(username.strip(),)).fetchone();c.close()
 if not r or not bcrypt.checkpw(password.encode(),r['password_hash'].encode()):raise HTTPException(401,'Incorrect username or password.')
 request.session.clear();request.session['user_id']=r['id'];return {'ok':True,'user':{'id':r['id'],'username':r['username']}}
@app.post('/api/auth/logout')
def logout(request:Request):request.session.clear();return {'ok':True}
@app.get('/api/entries')
def entries(request:Request):
 u=requser(request);c=db();rows=c.execute('SELECT * FROM entries WHERE user_id=? ORDER BY entry_date DESC,id DESC',(u['id'],)).fetchall();c.close();return {'entries':[jsonify(r,bool(r['is_locked'])) for r in rows]}
@app.post('/api/entries')
async def create(request:Request,title:str=Form(...),content:str=Form(...),entry_date:str=Form(...),mood:int=Form(4),theme:str=Form('auto'),lock_password:str=Form(''),photo:UploadFile|None=File(None)):
 u=requser(request);title=title.strip();content=content.strip();validdate(entry_date)
 if not title or not content:raise HTTPException(400,'Title and content are required.')
 if not 1<=mood<=7:raise HTTPException(400,'Mood must be between 1 and 7.')
 if len(lock_password) and len(lock_password)<4:raise HTTPException(400,'Entry password must be at least 4 characters.')
 locked=bool(lock_password);c=db();t=now();cur=c.execute('INSERT INTO entries(user_id,title,content,entry_date,mood,theme,is_locked,lock_hash,photo_path,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(u['id'],title,content,entry_date,mood,theme,int(locked),bcrypt.hashpw(lock_password.encode(),bcrypt.gensalt()).decode() if locked else None,None,t,t));eid=cur.lastrowid
 if photo and photo.filename:
  if photo.content_type not in ALLOWED:c.rollback();c.close();raise HTTPException(400,'Only JPG, PNG, WEBP, and GIF images are allowed.')
  raw=await photo.read()
  if len(raw)>MAX:c.rollback();c.close();raise HTTPException(400,'Photo must be 8 MB or smaller.')
  fn=f"user_{u['id']}_entry_{eid}_{secrets.token_hex(8)}{Path(photo.filename).suffix.lower()}";(UPLOADS/fn).write_bytes(raw);c.execute('UPDATE entries SET photo_path=? WHERE id=?',(fn,eid))
 c.commit();r=c.execute('SELECT * FROM entries WHERE id=? AND user_id=?',(eid,u['id'])).fetchone();c.close();return jsonify(r)
@app.post('/api/entries/{eid}/unlock')
def unlock(request:Request,eid:int,password:str=Form(...)):
 u=requser(request);c=db();r=c.execute('SELECT * FROM entries WHERE id=? AND user_id=?',(eid,u['id'])).fetchone();c.close()
 if not r:raise HTTPException(404,'Entry not found.')
 if r['is_locked'] and (not r['lock_hash'] or not bcrypt.checkpw(password.encode(),r['lock_hash'].encode())):raise HTTPException(403,'Incorrect entry password.')
 return jsonify(r)
@app.delete('/api/entries/{eid}')
def delete(request:Request,eid:int):
 u=requser(request);c=db();r=c.execute('SELECT * FROM entries WHERE id=? AND user_id=?',(eid,u['id'])).fetchone()
 if not r:c.close();raise HTTPException(404,'Entry not found.')
 if r['photo_path']:(UPLOADS/r['photo_path']).unlink(missing_ok=True)
 c.execute('DELETE FROM entries WHERE id=? AND user_id=?',(eid,u['id']));c.commit();c.close();return {'ok':True}
@app.get('/api/calendar/{year}/{month}')
def calendar(request:Request,year:int,month:int):
 u=requser(request);c=db();rows=c.execute("SELECT id,title,entry_date,mood,is_locked,theme FROM entries WHERE user_id=? AND strftime('%Y',entry_date)=? AND strftime('%m',entry_date)=? ORDER BY entry_date,id",(u['id'],f'{year:04d}',f'{month:02d}')).fetchall();c.close();return {'entries':[dict(r) for r in rows]}
@app.get('/api/stats')
def stats(request:Request):
 u=requser(request);c=db();count=c.execute('SELECT COUNT(*) c FROM entries WHERE user_id=?',(u['id'],)).fetchone()['c'];avg=c.execute('SELECT AVG(mood) a FROM entries WHERE user_id=?',(u['id'],)).fetchone()['a'];dates=[r['entry_date'] for r in c.execute('SELECT DISTINCT entry_date FROM entries WHERE user_id=? ORDER BY entry_date DESC',(u['id'],)).fetchall()];c.close();streak=0
 if dates:
  from datetime import timedelta
  d=date.fromisoformat(dates[0])
  while d.isoformat() in dates:streak+=1;d-=timedelta(days=1)
 return {'entry_count':count,'average_mood':round(avg,1) if avg else None,'streak':streak}
@app.get('/api/uploads/{eid}')
def photo(request:Request,eid:int):
 u=requser(request);c=db();r=c.execute('SELECT photo_path FROM entries WHERE id=? AND user_id=?',(eid,u['id'])).fetchone();c.close()
 if not r or not r['photo_path']:raise HTTPException(404,'Photo not found.')
 p=UPLOADS/r['photo_path']
 if not p.exists():raise HTTPException(404,'Photo file not found.')
 return FileResponse(p)
@app.get('/')
def index():return FileResponse(FRONT/'index.html')
app.mount('/static',StaticFiles(directory=FRONT/'static'),name='static')
