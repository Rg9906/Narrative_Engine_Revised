"""In-memory job tracking for chapter ingestion.

Ingestion runs the real NLP pipeline (spaCy / GLiNER / FastCoref) plus LLM calls, which
can take anywhere from a few seconds (cache hit) to a couple of minutes. FastAPI's
BackgroundTasks hands the blocking call to a worker thread after the upload response is
sent; this module is the shared, process-local dict the frontend polls against.

Single-process, in-memory job state is enough here — this is a local developer tool
serving one dashboard, not a distributed service.
"""

from __future__ import annotations

import logging
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

JobStatus = Literal["pending", "running", "done", "error"]

logger = logging.getLogger("NarrativeEngine.API.Jobs")

_JOBS: dict[str, dict[str, Any]] = {}


def create_job(filename: str) -> str:
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {
        "id": job_id,
        "filename": filename,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "finished_at": None,
        "result": None,
        "error": None,
    }
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    return _JOBS.get(job_id)


def list_jobs() -> list[dict[str, Any]]:
    return sorted(_JOBS.values(), key=lambda j: j["created_at"], reverse=True)


def run_ingest_job(job_id: str, chapter_path: Path) -> None:
    job = _JOBS[job_id]
    job["status"] = "running"
    try:
        # Imported lazily: this pulls in spaCy/GLiNER/FastCoref, which read endpoints
        # should never have to pay the startup cost for.
        from src.main import process_chapter

        result = process_chapter(str(chapter_path))
        job["result"] = result
        job["status"] = "done"
    except Exception as e:
        logger.error(f"Ingestion job {job_id} failed: {e}")
        job["error"] = {"message": str(e), "traceback": traceback.format_exc()}
        job["status"] = "error"
    finally:
        job["finished_at"] = datetime.now().isoformat()
