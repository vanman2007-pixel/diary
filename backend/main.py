from pathlib import Path
from datetime import datetime, date
import sqlite3
import uuid
import hashlib
import secrets
import base64
import mimetypes

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from passlib.context import CryptContext

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
UPLOADS = DATA / "uploads"
FRONTEND = BASE / "frontend"
DATA.mkdir(exist_ok=True)
UPLOADS.mkdir(exist_ok=True)

DB = DATA / "diary.db"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Diary", version="1.0.0")
app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            entry_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            mood INTEGER NOT NULL DEFAULT 4,
            theme TEXT NOT NULL DEFAULT 'auto',
            photo_path TEXT,
            locked INTEGER NOT NULL DEFAULT 0,
            password_hash TEXT
        )
    """)
    conn.commit()
    return conn

def row_dict(row):
    d = dict(row)
    d["locked"] = bool(d["locked"])
    if d["locked"]:
        d["content"] = None
        d["title"] = "Locked entry"
        d["photo_path"] = None
    return d

class EntryIn(BaseModel):
    title: str = ""
    content: str
    entry_date: str
    mood: int = 4
    theme: str = "auto"
    password: str | None = None

class UnlockIn(BaseModel):
    password: str

@app.get("/", response_class=HTMLResponse)
def home():
    return (FRONTEND / "index.html").read_text(encoding="utf-8")

@app.get("/api/entries")
def get_entries():
    conn = db()
    rows = conn.execute("SELECT * FROM entries ORDER BY entry_date DESC, created_at DESC").fetchall()
    conn.close()
    return [row_dict(r) for r in rows]

@app.get("/api/calendar/{year}/{month}")
def calendar(year: int, month: int):
    if month < 1 or month > 12:
        raise HTTPException(400, "Invalid month")
    conn = db()
    rows = conn.execute(
        "SELECT entry_date, mood, theme, COUNT(*) count FROM entries "
        "WHERE entry_date LIKE ? GROUP BY entry_date",
        (f"{year:04d}-{month:02d}-%",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/entries")
async def create_entry(
    title: str = Form(""),
    content: str = Form(...),
    entry_date: str = Form(...),
    mood: int = Form(4),
    theme: str = Form("auto"),
    password: str = Form(""),
    photo: UploadFile | None = File(None)
):
    if not content.strip():
        raise HTTPException(400, "Diary content cannot be empty")
    if mood < 1 or mood > 7:
        raise HTTPException(400, "Mood must be between 1 and 7")
    try:
        date.fromisoformat(entry_date)
    except ValueError:
        raise HTTPException(400, "Invalid date")

    photo_path = None
    if photo and photo.filename:
        allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        if photo.content_type not in allowed:
            raise HTTPException(400, "Only JPG, PNG, WEBP and GIF images are allowed")
        raw = await photo.read()
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(400, "Photo must be 8 MB or smaller")
        ext = mimetypes.guess_extension(photo.content_type) or ".img"
        name = f"{uuid.uuid4().hex}{ext}"
        (UPLOADS / name).write_bytes(raw)
        photo_path = f"/uploads/{name}"

    locked = bool(password.strip())
    password_hash = pwd_context.hash(password) if locked else None
    now = datetime.now().isoformat(timespec="seconds")
    entry_id = uuid.uuid4().hex

    conn = db()
    conn.execute(
        """INSERT INTO entries
        (id,title,content,entry_date,created_at,updated_at,mood,theme,photo_path,locked,password_hash)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (entry_id, title.strip(), content.strip(), entry_date, now, now,
         mood, theme, photo_path, int(locked), password_hash)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
    conn.close()
    return row_dict(row)

@app.post("/api/entries/{entry_id}/unlock")
def unlock(entry_id: str, body: UnlockIn):
    conn = db()
    row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Entry not found")
    if not row["locked"]:
        return dict(row)
    if not row["password_hash"] or not pwd_context.verify(body.password, row["password_hash"]):
        raise HTTPException(401, "Incorrect password")
    return dict(row)

@app.delete("/api/entries/{entry_id}")
def delete_entry(entry_id: str):
    conn = db()
    row = conn.execute("SELECT photo_path FROM entries WHERE id=?", (entry_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Entry not found")
    conn.execute("DELETE FROM entries WHERE id=?", (entry_id,))
    conn.commit()
    conn.close()
    if row["photo_path"]:
        p = BASE / "data" / row["photo_path"].removeprefix("/uploads/")
        if p.exists():
            p.unlink()
    return {"ok": True}

@app.get("/api/stats")
def stats():
    conn = db()
    total = conn.execute("SELECT COUNT(*) c FROM entries").fetchone()["c"]
    days = conn.execute("SELECT COUNT(DISTINCT entry_date) c FROM entries").fetchone()["c"]
    moods = conn.execute("SELECT mood, COUNT(*) c FROM entries GROUP BY mood ORDER BY c DESC").fetchall()
    conn.close()
    return {"entries": total, "days": days, "moods": [dict(x) for x in moods]}
