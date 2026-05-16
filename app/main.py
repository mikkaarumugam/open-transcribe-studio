from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.services.exporters import write_exports
from app.services.transcription import TranscriptionError, transcribe_file

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
for directory in (UPLOAD_DIR, EXPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Open Transcribe Studio",
    description="Free local-first Gladia-inspired transcription studio.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")

EXPORT_INDEX: dict[str, dict[str, str]] = {}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/transcribe")
async def api_transcribe(file: UploadFile = File(...), model_size: str = Form("tiny")):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload must include a filename")
    safe_name = Path(file.filename).name
    job_stub = str(uuid.uuid4())
    upload_path = UPLOAD_DIR / f"{job_stub}-{safe_name}"
    with upload_path.open("wb") as out_file:
        shutil.copyfileobj(file.file, out_file)

    try:
        result = transcribe_file(upload_path, filename=safe_name, model_size=model_size)
    except TranscriptionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    exports = write_exports(result, EXPORT_DIR)
    EXPORT_INDEX[result.job_id] = exports
    payload = result.model_dump()
    payload["exports"] = {kind: f"/api/exports/{result.job_id}/{kind}" for kind in exports}
    return payload


@app.get("/api/exports/{job_id}/{kind}")
def download_export(job_id: str, kind: str):
    if kind not in {"txt", "json", "srt", "vtt"}:
        raise HTTPException(status_code=400, detail="Export kind must be txt, json, srt, or vtt")
    path = EXPORT_INDEX.get(job_id, {}).get(kind) or str(EXPORT_DIR / f"{job_id}.{kind}")
    export_path = Path(path)
    if not export_path.exists():
        raise HTTPException(status_code=404, detail="Export not found")
    return FileResponse(export_path, filename=export_path.name)
