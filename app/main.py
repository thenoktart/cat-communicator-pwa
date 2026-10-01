from __future__ import annotations

import mimetypes
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RECORDINGS_DIR = DATA_DIR / "recordings"
DB_PATH = DATA_DIR / "cat_data.sqlite3"
STATIC_DIR = Path(__file__).resolve().parent / "static"

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Cat Communicator MVP", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def supabase_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    if extra:
        headers.update(extra)
    return headers


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    if USE_SUPABASE:
        return
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
    return {"ok": True, "storage": "supabase" if USE_SUPABASE else "local"}


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


async def save_to_supabase(
    *,
    record_id: str,
    created_at: str,
    content: bytes,
    mime_type: str,
    suffix: str,
    cat_name: str,
    label: str,
    context: str,
    outcome: str,
    notes: str,
    duration_ms: int | None,
) -> None:
    audio_path = f"{cat_name.strip() or 'Kedim'}/{record_id}{suffix}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        upload = await client.post(
            f"{SUPABASE_URL}/storage/v1/object/cat-audio/{audio_path}",
            headers=supabase_headers({
                "Content-Type": mime_type,
                "x-upsert": "false",
            }),
            content=content,
        )
        if upload.status_code >= 300:
            raise HTTPException(
                status_code=502,
                detail=f"Ses buluta yüklenemedi: {upload.text[:200]}",
            )

        row = {
            "id": record_id,
            "created_at": created_at,
            "cat_name": cat_name.strip() or "Kedim",
            "label": label,
            "context": context.strip(),
            "outcome": outcome.strip(),
            "notes": notes.strip(),
            "duration_ms": duration_ms,
            "mime_type": mime_type,
            "audio_path": audio_path,
        }

        insert = await client.post(
            f"{SUPABASE_URL}/rest/v1/vocalizations",
            headers=supabase_headers({
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            }),
            json=row,
        )
        if insert.status_code >= 300:
            # Audio exists but metadata failed; leave it for manual recovery rather than deleting blindly.
            raise HTTPException(
                status_code=502,
                detail=f"Kayıt bilgisi buluta yazılamadı: {insert.text[:200]}",
            )


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
    created_at = datetime.now(timezone.utc).isoformat()

    if USE_SUPABASE:
        await save_to_supabase(
            record_id=record_id,
            created_at=created_at,
            content=content,
            mime_type=mime_type,
            suffix=suffix,
            cat_name=cat_name,
            label=label,
            context=context,
            outcome=outcome,
            notes=notes,
            duration_ms=duration_ms,
        )
    else:
        target = RECORDINGS_DIR / f"{record_id}{suffix}"
        target.write_bytes(content)
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

    return {
        "ok": True,
        "id": record_id,
        "created_at": created_at,
        "storage": "supabase" if USE_SUPABASE else "local",
    }


@app.get("/api/records")
async def list_records(limit: int = 50):
    limit = max(1, min(limit, 200))

    if USE_SUPABASE:
        params = {
            "select": "id,created_at,cat_name,label,context,outcome,notes,duration_ms,mime_type",
            "order": "created_at.desc",
            "limit": str(limit),
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/vocalizations",
                headers=supabase_headers(),
                params=params,
            )
        if response.status_code >= 300:
            raise HTTPException(status_code=502, detail="Bulut kayıtları okunamadı.")
        return response.json()

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
async def stats():
    if USE_SUPABASE:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/vocalizations",
                headers=supabase_headers(),
                params={"select": "label"},
            )
        if response.status_code >= 300:
            raise HTTPException(status_code=502, detail="Bulut istatistikleri okunamadı.")
        rows = response.json()
        counts: dict[str, int] = {}
        for row in rows:
            label = row.get("label", "unknown")
            counts[label] = counts.get(label, 0) + 1
        by_label = [
            {"label": label, "count": count}
            for label, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        ]
        return {
            "total": len(rows),
            "by_label": by_label,
            "target_for_first_model": 200,
            "storage": "supabase",
        }

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
        "storage": "local",
    }
