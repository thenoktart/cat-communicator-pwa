from __future__ import annotations

import mimetypes
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RECORDINGS_DIR = DATA_DIR / "recordings"
DB_PATH = DATA_DIR / "cat_data.sqlite3"
STATIC_DIR = Path(__file__).resolve().parent / "static"

RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Cat Communicator MVP", version="0.1.1")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vocalizations (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                cat_name TEXT NOT NULL,
                label TEXT NOT NULL,
                context TEXT NOT NULL,
                outcome TEXT NOT NULL,
                notes TEXT NOT NULL,
                duration_ms INTEGER,
                mime_type TEXT NOT NULL,
                audio_path TEXT NOT NULL
            )
            """
        )
        conn.commit()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"ok": True}


def suffix_for_mime(mime: str) -> str:
    clean = (mime or "").split(";")[0].strip().lower()
    known = {
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/mpeg": ".mp3",
    }
    return known.get(clean) or mimetypes.guess_extension(clean) or ".audio"


@app.post("/api/records")
async def create_record(
    audio: UploadFile = File(...),
    cat_name: str = Form(...),
    label: str = Form(...),
    context: str = Form(""),
    outcome: str = Form(""),
    notes: str = Form(""),
    duration_ms: int | None = Form(None),
):
    allowed_labels = {
        "food", "attention", "play", "door", "greeting", "stress", "unknown"
    }
    if label not in allowed_labels:
        raise HTTPException(status_code=400, detail="Geçersiz etiket.")

    content = await audio.read()
    if not content:
        raise HTTPException(status_code=400, detail="Ses dosyası boş.")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Ses dosyası 10 MB sınırını aşıyor.")

    mime_type = audio.content_type or "application/octet-stream"
    record_id = str(uuid.uuid4())
    suffix = suffix_for_mime(mime_type)
    target = RECORDINGS_DIR / f"{record_id}{suffix}"
    target.write_bytes(content)

    created_at = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO vocalizations
            (id, created_at, cat_name, label, context, outcome, notes,
             duration_ms, mime_type, audio_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                created_at,
                cat_name.strip() or "Kedim",
                label,
                context.strip(),
                outcome.strip(),
                notes.strip(),
                duration_ms,
                mime_type,
                str(target.relative_to(BASE_DIR)),
            ),
        )
        conn.commit()

    return {"ok": True, "id": record_id, "created_at": created_at}


@app.get("/api/records")
def list_records(limit: int = 50):
    limit = max(1, min(limit, 200))
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, cat_name, label, context, outcome,
                   notes, duration_ms, mime_type
            FROM vocalizations
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/stats")
def stats():
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM vocalizations").fetchone()[0]
        rows = conn.execute(
            """
            SELECT label, COUNT(*) AS count
            FROM vocalizations
            GROUP BY label
            ORDER BY count DESC
            """
        ).fetchall()
    return {
        "total": total,
        "by_label": [{"label": row["label"], "count": row["count"]} for row in rows],
        "target_for_first_model": 200,
    }
