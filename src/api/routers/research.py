import asyncio
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, WebSocket
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.agents.research.agents import RephraseAgent
from src.logging import get_logger
from src.services.config import load_config_with_main
from src.services.export.pdf_generator import PDFGenerator

# Import the new PPTGenerator service
from src.services.export.ppt_generator import PPTGenerator
from src.services.export.ppt_project_service import get_ppt_project_service
from src.services.export.source_report import SourceReportGenerator
from src.services.llm import get_llm_config
from src.services.research import get_research_run_service
from src.services.research.run_config import build_research_paths
from src.services.storage.file_store import get_file_record
from src.services.storage.object_store import get_object_stream

# Force stdout to use utf-8 to prevent encoding errors with emojis on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

router = APIRouter()
_DEPRECATED_PPT_HEADER = "X-DeepTutor-Deprecated"


# Helper to load config (with main.yaml merge)
def load_config():
    project_root = Path(__file__).parent.parent.parent.parent
    return load_config_with_main("research_config.yaml", project_root)


def _project_root() -> Path:
    return Path(__file__).parent.parent.parent.parent


def _ppt_service():
    return get_ppt_project_service(_project_root())


def _research_service():
    return get_research_run_service(_project_root())


def _mark_ppt_deprecated(response: Response) -> None:
    response.headers[_DEPRECATED_PPT_HEADER] = "true"


def _deprecated_http_exception(status_code: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={_DEPRECATED_PPT_HEADER: "true"},
    )


async def _wait_for_ppt_task(project_id: str, task_id: str) -> dict[str, Any]:
    service = _ppt_service()
    while True:
        task = service.get_task(project_id, task_id)
        if not task:
            raise _deprecated_http_exception(status_code=404, detail="PPT task not found")
        if task["status"] == "COMPLETED":
            return task
        if task["status"] in {"FAILED", "CANCELED"}:
            raise _deprecated_http_exception(
                status_code=500,
                detail=task.get("error_message") or "PPT task failed",
            )
        await asyncio.sleep(1.5)


def _read_json_file(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _file_sha256(path: Path) -> str | None:
    try:
        data = path.read_bytes()
        return hashlib.sha256(data).hexdigest()
    except Exception:
        return None


def _get_latest_event(progress: dict | None) -> dict | None:
    if not progress:
        return None
    events = progress.get("events") or []
    if not events:
        return None
    return events[-1]


def _output_url_for_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    project_root = _project_root()
    user_root = project_root / "data" / "user"
    try:
        relative = path.relative_to(user_root)
    except ValueError:
        return None
    return f"/api/outputs/{relative.as_posix()}"


def _metadata_from_path(path_value: str | None) -> dict | None:
    if not path_value:
        return None
    path = Path(path_value)
    return _read_json_file(path)


def _status_payload_from_run(run: dict[str, Any]) -> dict[str, Any]:
    report_url = _output_url_for_path(run.get("report_path"))
    metadata = _metadata_from_path(run.get("metadata_path"))
    has_report = bool(report_url)
    status = run.get("status") or "PENDING"
    phase = (run.get("phase") or "PLANNING").lower()
    if status == "COMPLETED":
        stage = "completed"
    elif status in {"FAILED", "CANCELLED"}:
        stage = "failed"
    else:
        stage = phase
    return {
        "research_id": run["research_id"],
        "run_id": run["id"],
        "task_status": status,
        "stage": stage,
        "has_report": has_report,
        "report_url": report_url,
        "metadata": metadata,
        "report_metadata_url": _output_url_for_path(run.get("metadata_path")),
        "progress": run.get("progress") or {},
        "checkpoint": run.get("checkpoint") or {},
        "error_message": run.get("error_message"),
    }


def _legacy_status_is_stale(progress: dict | None, *, stale_seconds: int = 120) -> bool:
    event = _get_latest_event(progress)
    if not event:
        return False
    timestamp = event.get("timestamp")
    if not timestamp:
        return False
    try:
        last_update = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).timestamp()
    except Exception:
        return False
    return time.time() - last_update > stale_seconds


# Initialize logger with config
config = load_config()
log_dir = config.get("paths", {}).get("user_log_dir") or config.get("logging", {}).get("log_dir")
logger = get_logger("ResearchAPI", log_dir=log_dir)


class OptimizeRequest(BaseModel):
    topic: str
    iteration: int = 0
    previous_result: dict[str, Any] | None = None
    kb_name: str | None = "ai_textbook"


class CreateResearchRunRequest(BaseModel):
    topic: str
    kb_name: str | None = "ai_textbook"
    notebook_id: str | None = None
    session_id: str | None = None
    plan_mode: Literal["quick", "medium", "deep", "auto"] = "medium"
    enabled_tools: list[str] | None = None
    skip_rephrase: bool = False
    preset: str | None = None
    research_mode: str | None = None


class ExportPptxRequest(BaseModel):
    markdown: str
    title: str | None = None
    max_slides: int = 15
    style_prompt: str | None = None
    style_model: str | None = None
    style_api_key: str | None = None
    style_base_url: str | None = None
    template_name: str | None = None


class ExportPdfRequest(BaseModel):
    markdown: str
    title: str | None = None


class SourceItem(BaseModel):
    type: Literal["web", "kb", "file", "report"]
    title: str
    url: str | None = None
    content: str | None = None


class ComposeFromSourcesRequest(BaseModel):
    sources: list[SourceItem]
    topic: str | None = None


class PptStyleFromSourcesRequest(BaseModel):
    sources: list[SourceItem]
    topic: str | None = None


class PptStylePreviewRequest(BaseModel):
    style_prompt: str | None = None


class BananaPptOutlineRequest(BaseModel):
    source_content: str
    style_prompt: str | None = None
    max_slides: int | None = None


class BananaPptImageRequest(BaseModel):
    prompt: str
    slide_title: str | None = None
    slide_points: list[str] | None = None
    layout: str | None = None
    deck_title: str | None = None
    style_prompt: str | None = None


@router.post("/export_pptx")
async def export_pptx(request: ExportPptxRequest, response: Response):
    _mark_ppt_deprecated(response)
    project_root = _project_root()
    export_dir = project_root / "data" / "user" / "research" / "exports"
    template_dir = project_root / "data" / "user" / "notebook" / "ppt_templates"

    if request.template_name:
        generator = PPTGenerator(export_dir=export_dir)
        try:
            candidate = template_dir / request.template_name
            if not candidate.exists():
                raise _deprecated_http_exception(status_code=404, detail="Template not found")
            return await generator.generate(
                markdown=request.markdown,
                title=request.title,
                style_prompt=request.style_prompt,
                style_model=request.style_model,
                style_api_key=request.style_api_key,
                style_base_url=request.style_base_url,
                max_slides=request.max_slides,
                template_path=candidate,
            )
        except HTTPException:
            raise
        except ImportError as exc:
            raise _deprecated_http_exception(
                status_code=500,
                detail=f"PPT export dependencies not installed: {exc}",
            )
        except Exception as exc:
            logger.error(f"Legacy PPT export failed: {exc}")
            raise _deprecated_http_exception(status_code=500, detail=str(exc))

    try:
        service = _ppt_service()
        project = service.create_project(
            notebook_id=None,
            session_id=None,
            creation_type="descriptions",
            idea_prompt=None,
            outline_text=None,
            description_text=request.markdown,
            source_content=request.markdown,
            template_style=request.style_prompt,
            template_image_path=None,
            reference_style_prompt=None,
            image_aspect_ratio="16:9",
            language="zh",
            reference_sources=[],
        )
        await service.generate_outline(project["id"], max_slides=request.max_slides)
        description_task = service.start_generate_descriptions(project["id"])
        await _wait_for_ppt_task(project["id"], description_task["id"])
        image_task = service.start_generate_images(project["id"])
        await _wait_for_ppt_task(project["id"], image_task["id"])
        return service.export_pptx_with_title(
            project["id"],
            title_override=request.title,
        )
    except HTTPException:
        raise
    except ImportError as exc:
        raise _deprecated_http_exception(
            status_code=500,
            detail=f"PPT export dependencies not installed: {exc}",
        )
    except Exception as exc:
        logger.error(f"PPT export compatibility path failed: {exc}")
        raise _deprecated_http_exception(status_code=500, detail=str(exc))


@router.get("/pptx/{file_id}")
async def download_pptx(file_id: str):
    record = get_file_record(file_id)
    if not record or record.get("file_type") != "pptx":
        raise HTTPException(status_code=404, detail="PPT not found")
    response = get_object_stream(record["bucket"], record["object_key"])

    def iter_stream():
        try:
            for chunk in response.stream(8192):
                if chunk:
                    yield chunk
        finally:
            response.close()
            response.release_conn()

    return StreamingResponse(
        iter_stream(),
        media_type=record["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{record["filename"]}"'},
    )


@router.post("/export_pdf")
async def export_pdf(request: ExportPdfRequest):
    project_root = Path(__file__).parent.parent.parent.parent
    export_dir = project_root / "data" / "user" / "notebook" / "exports"

    generator = PDFGenerator(export_dir=export_dir)

    try:
        result = await generator.generate(
            markdown=request.markdown,
            title=request.title,
        )
        return result
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"PDF export dependencies not installed: {e}",
        )
    except Exception as e:
        logger.error(f"PDF Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ppt_style_templates")
async def list_ppt_style_templates(response: Response):
    _mark_ppt_deprecated(response)
    config = _ppt_service().get_config()
    return {"templates": config.get("style_templates") or []}


@router.post("/compose_from_sources")
async def compose_from_sources(request: ComposeFromSourcesRequest):
    try:
        generator = SourceReportGenerator()
        result = await generator.generate(
            sources=[s.model_dump() for s in request.sources],
            topic=request.topic,
        )
        return result
    except Exception as e:
        logger.error(f"Source report generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ppt_style_from_sources")
async def ppt_style_from_sources(request: PptStyleFromSourcesRequest):
    try:
        generator = SourceReportGenerator()
        result = await generator.generate_style_prompt(
            sources=[s.model_dump() for s in request.sources],
            topic=request.topic,
        )
        return result
    except Exception as e:
        logger.error(f"PPT style generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ppt_style_preview")
async def ppt_style_preview(request: PptStylePreviewRequest, response: Response):
    _mark_ppt_deprecated(response)
    try:
        return await _ppt_service().preview_style(request.style_prompt)
    except Exception as exc:
        logger.error(f"PPT style preview failed: {exc}")
        raise _deprecated_http_exception(status_code=500, detail=str(exc))


@router.get("/ppt_config")
async def get_ppt_config_for_banana(response: Response):
    _mark_ppt_deprecated(response)
    config = _ppt_service().get_config()
    return {
        "enabled": config.get("enabled", True),
        "max_slides": config.get("max_slides", 15),
        "style_templates": config.get("style_templates") or [],
    }


@router.post("/ppt_outline")
async def generate_ppt_outline(request: BananaPptOutlineRequest, response: Response):
    _mark_ppt_deprecated(response)
    config = _ppt_service().get_config()
    if not config.get("enabled", True):
        raise _deprecated_http_exception(status_code=403, detail="Banana PPT is disabled")

    try:
        result = await _ppt_service().derive_outline(
            request.source_content,
            style_prompt=request.style_prompt,
            max_slides=request.max_slides,
        )
        return result["presentation_outline"]
    except Exception as exc:
        logger.error(f"Banana PPT outline failed: {exc}")
        raise _deprecated_http_exception(status_code=500, detail=str(exc))


@router.post("/ppt_image")
async def generate_ppt_image(request: BananaPptImageRequest, response: Response):
    _mark_ppt_deprecated(response)
    config = _ppt_service().get_config()
    if not config.get("enabled", True):
        raise _deprecated_http_exception(status_code=403, detail="Banana PPT is disabled")

    try:
        return await _ppt_service().generate_image_preview(
            prompt=request.prompt,
            slide_title=request.slide_title,
            slide_points=request.slide_points,
            layout=request.layout,
            deck_title=request.deck_title,
            style_prompt=request.style_prompt,
        )
    except Exception as exc:
        logger.error(f"Banana PPT image failed: {exc}")
        raise _deprecated_http_exception(status_code=500, detail=str(exc))


@router.get("/ppt_templates")
async def list_ppt_templates(response: Response):
    _mark_ppt_deprecated(response)
    project_root = _project_root()
    template_dir = project_root / "data" / "user" / "notebook" / "ppt_templates"
    template_dir.mkdir(parents=True, exist_ok=True)

    templates = []
    for path in template_dir.iterdir():
        if not path.is_file() or path.suffix.lower() != ".pptx":
            continue
        stat = path.stat()
        templates.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "download_url": f"/api/outputs/notebook/ppt_templates/{path.name}",
            }
        )

    templates.sort(key=lambda item: item["modified_at"], reverse=True)
    return {"templates": templates}


@router.post("/ppt_templates/upload")
async def upload_ppt_template(response: Response, file: UploadFile = File(...)):
    _mark_ppt_deprecated(response)
    project_root = _project_root()
    template_dir = project_root / "data" / "user" / "notebook" / "ppt_templates"
    template_dir.mkdir(parents=True, exist_ok=True)

    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise _deprecated_http_exception(
            status_code=400,
            detail="Only .pptx templates are supported",
        )

    safe_name = Path(file.filename).name.replace("/", "_").replace("\\", "_")
    target_path = template_dir / safe_name
    content = await file.read()
    target_path.write_bytes(content)

    return {"success": True, "name": safe_name}


@router.post("/optimize_topic")
async def optimize_topic(request: OptimizeRequest):
    try:
        config = load_config()

        # Inject API keys
        try:
            llm_config = get_llm_config()
            api_key = llm_config.api_key
            base_url = llm_config.base_url
        except Exception as e:
            return {"error": f"LLM config error: {e!s}"}

        # Init Agent
        agent = RephraseAgent(config=config, api_key=api_key, base_url=base_url)

        # Process
        # If iteration > 0, topic is treated as feedback
        if request.iteration == 0:
            result = await agent.process(request.topic, iteration=0)
        else:
            result = await agent.process(
                request.topic, iteration=request.iteration, previous_result=request.previous_result
            )

        return result

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}


@router.post("/runs")
async def create_research_run(request: CreateResearchRunRequest):
    if not request.topic.strip():
        raise HTTPException(status_code=400, detail="Topic is required")
    run, attached = _research_service().create_or_attach_run(
        notebook_id=request.notebook_id,
        session_id=request.session_id,
        topic=request.topic.strip(),
        kb_name=request.kb_name,
        plan_mode=request.plan_mode,
        enabled_tools=request.enabled_tools,
        skip_rephrase=request.skip_rephrase,
        preset=request.preset,
        research_mode=request.research_mode,
    )
    return {"run": run, "task_id": run["id"], "attached_existing": attached}


@router.get("/runs/{run_id}")
async def get_research_run(run_id: str):
    run = _research_service().get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Research run not found")
    return _status_payload_from_run(run)


@router.get("/runs/{run_id}/events")
async def get_research_run_events(run_id: str, after_id: int = Query(0, ge=0)):
    run = _research_service().get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Research run not found")
    events = _research_service().list_events(run_id, after_id=after_id)
    return {"run_id": run_id, "events": events}


@router.post("/runs/{run_id}/cancel")
async def cancel_research_run(run_id: str):
    run = _research_service().cancel_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Research run not found")
    return {"run": run}


@router.get("/runs/by-research-id/{research_id}")
async def get_research_run_by_research_id(research_id: str):
    run = _research_service().get_run_by_research_id(research_id)
    if not run:
        raise HTTPException(status_code=404, detail="Research run not found")
    return {"run": run}


@router.get("/status/{research_id}")
async def research_status(research_id: str):
    run = _research_service().get_run_by_research_id(research_id)
    if run:
        payload = _status_payload_from_run(run)
        paths = build_research_paths(_project_root(), research_id)
        progress = {
            "planning": _read_json_file(paths["planning_progress_file"]),
            "researching": _read_json_file(paths["researching_progress_file"]),
            "reporting": _read_json_file(paths["reporting_progress_file"]),
        }
        payload.update(
            {
                "progress": progress,
                "latest_event": {
                    "planning": _get_latest_event(progress["planning"]),
                    "researching": _get_latest_event(progress["researching"]),
                    "reporting": _get_latest_event(progress["reporting"]),
                },
                "queue": _read_json_file(paths["queue_file"]),
            }
        )
        return payload

    project_root = _project_root()
    base_dir = project_root / "data" / "user" / "research"
    cache_dir = base_dir / "cache" / research_id
    reports_dir = base_dir / "reports"

    planning = _read_json_file(cache_dir / "planning_progress.json")
    researching = _read_json_file(cache_dir / "researching_progress.json")
    reporting = _read_json_file(cache_dir / "reporting_progress.json")
    queue = _read_json_file(cache_dir / "queue.json")

    report_file = reports_dir / f"{research_id}.md"
    metadata_file = reports_dir / f"{research_id}_metadata.json"
    has_report = report_file.exists()

    if (
        not any([planning, researching, reporting, queue])
        and not has_report
        and not metadata_file.exists()
    ):
        raise HTTPException(status_code=404, detail="Research not found")

    report_url = None
    report_size = None
    report_updated_at = None
    report_hash = None
    if has_report:
        report_url = f"/api/outputs/research/reports/{report_file.name}"
        stat = report_file.stat()
        report_size = stat.st_size
        report_updated_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
        report_hash = _file_sha256(report_file)

    metadata = _read_json_file(metadata_file)
    metadata_url = (
        f"/api/outputs/research/reports/{metadata_file.name}" if metadata_file.exists() else None
    )

    stage = "idle"
    error_message = None
    if has_report:
        stage = "completed"
    elif reporting and reporting.get("events"):
        stage = "failed" if _legacy_status_is_stale(reporting) else "reporting"
        if stage == "failed":
            error_message = "stale_legacy_run"
    elif researching and researching.get("events"):
        stage = "failed" if _legacy_status_is_stale(researching) else "researching"
        if stage == "failed":
            error_message = "stale_legacy_run"
    elif planning and planning.get("events"):
        stage = "failed" if _legacy_status_is_stale(planning) else "planning"
        if stage == "failed":
            error_message = "stale_legacy_run"

    return {
        "research_id": research_id,
        "stage": stage,
        "has_report": has_report,
        "report_url": report_url,
        "report_size": report_size,
        "report_updated_at": report_updated_at,
        "report_hash": report_hash,
        "metadata": metadata,
        "metadata_url": metadata_url,
        "progress": {
            "planning": planning,
            "researching": researching,
            "reporting": reporting,
        },
        "latest_event": {
            "planning": _get_latest_event(planning),
            "researching": _get_latest_event(researching),
            "reporting": _get_latest_event(reporting),
        },
        "queue": queue,
        "error_message": error_message,
    }


@router.get("/latest")
async def latest_research(topic: str | None = Query(default=None)):
    project_root = Path(__file__).parent.parent.parent.parent
    reports_dir = project_root / "data" / "user" / "research" / "reports"
    if not reports_dir.exists():
        raise HTTPException(status_code=404, detail="No research reports found")

    candidates: list[tuple[float, dict, Path]] = []
    for metadata_file in reports_dir.glob("*_metadata.json"):
        metadata = _read_json_file(metadata_file)
        if not metadata:
            continue
        if topic:
            topic_lower = topic.lower()
            haystack = " ".join(
                [
                    str(metadata.get("topic", "")),
                    str(metadata.get("optimized_topic", "")),
                ]
            ).lower()
            if topic_lower not in haystack:
                continue
        completed_at = metadata.get("completed_at")
        if completed_at:
            try:
                ts = datetime.fromisoformat(completed_at).timestamp()
            except ValueError:
                ts = metadata_file.stat().st_mtime
        else:
            ts = metadata_file.stat().st_mtime
        candidates.append((ts, metadata, metadata_file))

    if not candidates:
        raise HTTPException(status_code=404, detail="No matching research found")

    candidates.sort(key=lambda item: item[0], reverse=True)
    _, metadata, metadata_file = candidates[0]
    research_id = metadata.get("research_id") or metadata_file.name.replace("_metadata.json", "")
    report_file = reports_dir / f"{research_id}.md" if research_id else None
    report_url = (
        f"/api/outputs/research/reports/{report_file.name}"
        if report_file and report_file.exists()
        else None
    )
    metadata_url = f"/api/outputs/research/reports/{metadata_file.name}"

    return {
        "research_id": research_id,
        "metadata": metadata,
        "report_url": report_url,
        "metadata_url": metadata_url,
    }


@router.websocket("/run")
async def websocket_research_run(websocket: WebSocket):
    await websocket.accept()
    ws_connected = True
    service = _research_service()
    run_id: str | None = None
    last_event_id = 0

    async def safe_send(data: dict[str, Any]) -> bool:
        nonlocal ws_connected
        if not ws_connected:
            return False
        try:
            await websocket.send_json(data)
            return True
        except Exception as exc:
            logger.warning(f"Research websocket send failed ({type(exc).__name__}): {exc!r}")
            ws_connected = False
            return False

    try:
        payload = await websocket.receive_json()
        requested_run_id = str(payload.get("run_id") or "").strip() or None
        last_event_id = max(0, int(payload.get("last_event_id") or 0))
        topic = str(payload.get("topic") or "").strip()
        attached_existing = False

        if requested_run_id:
            run = service.get_run(requested_run_id)
            if not run:
                await safe_send({"type": "error", "content": "Research run not found"})
                return
            attached_existing = True
        else:
            if not topic:
                await safe_send({"type": "error", "content": "Topic is required"})
                return
            kb_name = payload.get("kb_name", "ai_textbook")
            notebook_id = payload.get("notebook_id")
            session_id = payload.get("session_id")
            plan_mode = payload.get("plan_mode", "medium")
            enabled_tools = payload.get("enabled_tools", ["RAG"])
            skip_rephrase = bool(payload.get("skip_rephrase", False))
            preset = payload.get("preset")
            research_mode = payload.get("research_mode")
            run, attached_existing = service.create_or_attach_run(
                notebook_id=notebook_id,
                session_id=session_id,
                topic=topic,
                kb_name=kb_name,
                plan_mode=plan_mode,
                enabled_tools=enabled_tools,
                skip_rephrase=skip_rephrase,
                preset=preset,
                research_mode=research_mode,
            )

        run_id = run["id"]
        await safe_send(
            {
                "type": "task_id",
                "task_id": run["id"],
                "run_id": run["id"],
                "research_id": run["research_id"],
            }
        )
        if attached_existing:
            await safe_send(
                {
                    "type": "status",
                    "content": "already_running",
                    "run_id": run["id"],
                    "research_id": run["research_id"],
                }
            )

        next_ping_at = time.time() + 30
        terminal_statuses = {"COMPLETED", "FAILED", "CANCELLED"}

        while ws_connected:
            events = service.list_events(run_id, after_id=last_event_id)
            for event in events:
                event_payload = dict(event.get("payload") or {})
                event_payload.setdefault("run_id", run_id)
                event_payload.setdefault("research_id", run["research_id"])
                event_payload["event_id"] = event["id"]
                if not await safe_send(event_payload):
                    break
                last_event_id = max(last_event_id, int(event["id"]))

            if not ws_connected:
                break

            latest_run = service.get_run(run_id)
            if not latest_run:
                await safe_send({"type": "error", "content": "Research run no longer exists"})
                break
            run = latest_run

            if run["status"] in terminal_statuses:
                pending_events = service.list_events(run_id, after_id=last_event_id)
                for event in pending_events:
                    event_payload = dict(event.get("payload") or {})
                    event_payload.setdefault("run_id", run_id)
                    event_payload.setdefault("research_id", run["research_id"])
                    event_payload["event_id"] = event["id"]
                    if not await safe_send(event_payload):
                        break
                    last_event_id = max(last_event_id, int(event["id"]))
                break

            now = time.time()
            if now >= next_ping_at:
                if not await safe_send(
                    {
                        "type": "ping",
                        "timestamp": datetime.now().isoformat(),
                        "run_id": run_id,
                        "research_id": run["research_id"],
                    }
                ):
                    break
                next_ping_at = now + 30

            await asyncio.sleep(1.0)

    except Exception as exc:
        await safe_send({"type": "error", "content": str(exc)})
        logger.error(f"Research websocket attach failed: {exc}", exc_info=True)


class ExportMindmapRequest(BaseModel):
    """Request model for mindmap export"""

    markdown: str
    use_llm: bool = False


@router.post("/export_mindmap")
async def export_mindmap(request: ExportMindmapRequest):
    """
    Generate Mermaid mindmap code from research report

    Args:
        markdown: Markdown content of the report
        use_llm: If True, use LLM for better structure extraction

    Returns:
        {"mindmap": "mermaid mindmap code"}
    """
    try:
        from src.services.export.mindmap_generator import (
            generate_mindmap_code,
        )

        if request.use_llm:
            # Get LLM config for enhanced generation
            try:
                llm_config = get_llm_config()
                # TODO: Implement LLM callable for mindmap generation
                # For now, use rule-based
                mindmap_code = generate_mindmap_code(request.markdown)
            except Exception:
                mindmap_code = generate_mindmap_code(request.markdown)
        else:
            mindmap_code = generate_mindmap_code(request.markdown)

        return {"mindmap": mindmap_code}

    except Exception as e:
        logger.error(f"Mindmap export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
