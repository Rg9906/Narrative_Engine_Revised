"""FastAPI app serving the Narrative Intelligence Engine dashboard.

Run with:
    uvicorn api.main:app --reload --port 8420
"""

from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from api import graph_data, jobs, reports_data, state_data
from api.deps import get_project_config

ALLOWED_CHAPTER_EXTENSIONS = {".txt", ".pdf", ".docx"}

app = FastAPI(title="Narrative Intelligence Engine API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Narrative state
# ---------------------------------------------------------------------------


@app.get("/api/state/summary")
def state_summary() -> dict:
    config = get_project_config()
    data = state_data.load_raw_state(config)
    return state_data.build_summary(data)


@app.get("/api/state/timeline")
def state_timeline() -> dict:
    config = get_project_config()
    data = state_data.load_raw_state(config)
    timeline = data.get("timeline", []) or []
    return {"events": sorted(timeline, key=lambda e: e.get("chapter", 0) if isinstance(e, dict) else 0)}


@app.get("/api/state/collections/{collection}")
def state_collection(collection: str) -> dict:
    if collection not in state_data.COLLECTION_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown collection: {collection}")
    config = get_project_config()
    data = state_data.load_raw_state(config)
    return {"collection": collection, "entities": state_data.list_entities(data, collection)}


@app.get("/api/state/collections/{collection}/{entity_id}")
def state_entity(collection: str, entity_id: str) -> dict:
    if collection not in state_data.COLLECTION_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown collection: {collection}")
    config = get_project_config()
    data = state_data.load_raw_state(config)
    entity = state_data.get_entity(data, collection, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{collection}/{entity_id} not found")
    return entity


@app.get("/api/evidence")
def evidence() -> dict:
    config = get_project_config()
    data = state_data.load_raw_state(config)
    return {"evidence": state_data.get_evidence(data)}


# ---------------------------------------------------------------------------
# Narrative graph
# ---------------------------------------------------------------------------


@app.get("/api/graph")
def graph() -> dict:
    config = get_project_config()
    return graph_data.load_graph(config)


# ---------------------------------------------------------------------------
# Editorial reports
# ---------------------------------------------------------------------------


@app.get("/api/reports")
def reports_list() -> dict:
    config = get_project_config()
    return {"reports": reports_data.list_reports(config)}


@app.get("/api/reports/{chapter}")
def reports_detail(chapter: int) -> dict:
    config = get_project_config()
    report = reports_data.get_report(config, chapter)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report for chapter {chapter}")
    return report


# ---------------------------------------------------------------------------
# Chapter ingestion
# ---------------------------------------------------------------------------


@app.post("/api/ingest")
async def ingest_chapter(file: UploadFile, background_tasks: BackgroundTasks) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_CHAPTER_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Use .txt, .pdf, or .docx.",
        )

    config = get_project_config()
    config.chapters_dir.mkdir(parents=True, exist_ok=True)
    dest_path = config.chapters_dir / (file.filename or "chapter.txt")

    contents = await file.read()
    dest_path.write_bytes(contents)

    job_id = jobs.create_job(filename=dest_path.name)
    background_tasks.add_task(jobs.run_ingest_job, job_id, dest_path)
    return {"job_id": job_id}


@app.get("/api/ingest/jobs")
def ingest_jobs() -> dict:
    return {"jobs": jobs.list_jobs()}


@app.get("/api/ingest/jobs/{job_id}")
def ingest_job_status(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id")
    return job
