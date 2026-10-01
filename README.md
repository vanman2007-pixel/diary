# Diary — Full Stack Python Journal

A personal diary web app built with FastAPI + SQLite + HTML/CSS/JavaScript.

Features:
- Create, edit, delete diary entries
- Automatic date/time
- Photo upload on entries
- Mood scale and mood-based themes
- Calendar with written/missed days
- Light/dark mode
- Custom visual themes
- Password-protected individual entries
- Secure password hashing
- SQLite persistence

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000

Photos are stored in `data/uploads`.
The database is created automatically at `data/diary.db`.
