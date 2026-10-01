# Private Diary

Multi-user private diary with account login, private entries/photos, entry locks, moods, themes, calendar hover previews, light/dark mode, and persistent storage support.

## Local Windows run

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000

## Production

Use persistent storage for `data/diary.db` and `data/uploads`. `render.yaml` is included for a Render web service with a persistent disk. Set a strong `SECRET_KEY` in production. Do not commit the database or uploads.
