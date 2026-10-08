"""
FileMind FastAPI local backend server + WebSocket event stream.

Exposes REST and WebSocket endpoints tailored for the FileMind Desktop / System Tray
and Next.js UI (`UI/file-mind-ui-design`).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.classifier import check_ollama_status
from app.config import Settings, settings
from app.database import FileMindDatabase
from app.pipeline import FileMindPipeline
from app.watcher import start_watcher

logger = logging.getLogger(__name__)


class ReviewAcceptRequest(BaseModel):
    category: str | None = None
    subcategory: str | None = None
    suggested_filename: str | None = None


class SettingsUpdateRequest(BaseModel):
    watched_dir: str | None = None
    organized_dir: str | None = None
    ollama_host: str | None = None
    gemma_model: str | None = None
    confidence_threshold: float | None = None
    threshold_percent: int | None = None  # UI slider sends 50..99
    auto_organize: bool | None = None
    rename_files: bool | None = None
    safe_mode_undo: bool | None = None
    ocr_enabled: bool | None = None
    low_confidence_action: str | None = None


class ScanRequest(BaseModel):
    path: str | None = None


def create_app(
    *,
    pipeline: FileMindPipeline | None = None,
    enable_watcher: bool = False,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Pass a custom *pipeline* in tests to isolate the database and directories.
    Set *enable_watcher=True* when running as a live background daemon.
    """
    active_pipeline = pipeline or FileMindPipeline()
    ws_clients: set[WebSocket] = set()
    loop_holder: dict[str, asyncio.AbstractEventLoop | None] = {"loop": None}
    observer_holder: dict[str, Any] = {"observer": None}

    async def _broadcast(message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(ws_clients):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            ws_clients.discard(ws)

    def _on_pipeline_event(message: dict[str, Any]) -> None:
        loop = loop_holder.get("loop")
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(_broadcast(message), loop)

    active_pipeline.add_listener(_on_pipeline_event)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop_holder["loop"] = asyncio.get_running_loop()
        if enable_watcher:
            active_pipeline.watched_dir.mkdir(parents=True, exist_ok=True)
            observer_holder["observer"] = start_watcher(
                on_event=active_pipeline.handle_file_event,
                watch_dir=active_pipeline.watched_dir,
                debounce_interval=settings.debounce_interval,
            )
        try:
            yield
        finally:
            obs = observer_holder.get("observer")
            if obs is not None:
                obs.stop()
                obs.join()
                observer_holder["observer"] = None

    app = FastAPI(
        title="FileMind (SortSense) Local AI Backend",
        description="Offline, privacy-first semantic file organizer powered by Gemma 4 & Ollama.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.pipeline = active_pipeline

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": "FileMind"}

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        all_files = active_pipeline.db.list_files(limit=500)
        organized_count = sum(1 for f in all_files if f["status"] in ("organized", "accepted"))
        review_count = sum(1 for f in all_files if f["status"] == "review")
        return {
            "status": "running",
            "watcher_active": observer_holder.get("observer") is not None,
            "watched_dir": str(active_pipeline.watched_dir),
            "organized_dir": str(active_pipeline.organized_dir),
            "organized_count": organized_count,
            "review_count": review_count,
            "ollama": check_ollama_status(settings.ollama_host),
        }

    @app.get("/api/dashboard")
    def get_dashboard() -> dict[str, Any]:
        recent = active_pipeline.db.list_files(limit=25)
        review_queue = active_pipeline.db.list_files(status="review", limit=100)
        categories = active_pipeline.db.get_category_summary()
        organized_count = sum(1 for f in recent if f["status"] in ("organized", "accepted"))
        return {
            "recentActivity": recent,
            "reviewQueue": review_queue,
            "fileCategories": categories,
            "organizedCount": organized_count,
            "reviewCount": len(review_queue),
        }

    @app.get("/api/files")
    def list_files(status: str | None = Query(default=None)) -> dict[str, Any]:
        files = active_pipeline.db.list_files(status=status, limit=200)
        categories = active_pipeline.db.get_category_summary()
        return {"files": files, "fileCategories": categories}

    @app.get("/api/review")
    def list_review_queue() -> dict[str, Any]:
        queue = active_pipeline.db.list_files(status="review", limit=200)
        return {"reviewQueue": queue, "count": len(queue)}

    @app.post("/api/review/{file_id}/accept")
    def accept_review(file_id: str, body: ReviewAcceptRequest | None = None) -> dict[str, Any]:
        req = body or ReviewAcceptRequest()
        try:
            updated = active_pipeline.accept_review_item(
                file_id,
                category=req.category,
                subcategory=req.subcategory,
                suggested_filename=req.suggested_filename,
            )
            return {"status": "ok", "file": updated}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/review/{file_id}/ignore")
    def ignore_review(file_id: str) -> dict[str, Any]:
        try:
            updated = active_pipeline.ignore_review_item(file_id)
            return {"status": "ok", "file": updated}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/undo/{file_id}")
    def undo_file(file_id: str) -> dict[str, Any]:
        try:
            updated = active_pipeline.undo_organized_file(file_id)
            return {"status": "ok", "file": updated}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/activity")
    def get_activity() -> dict[str, Any]:
        return {"auditLog": active_pipeline.db.get_audit_log_grouped()}

    @app.get("/api/search")
    def search(q: str = Query(default="")) -> dict[str, Any]:
        return {"query": q, "results": active_pipeline.db.search_files(q)}

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return {
            "watched_dir": str(settings.watched_dir),
            "organized_dir": str(settings.organized_dir),
            "ollama_host": settings.ollama_host,
            "gemma_model": settings.gemma_model,
            "confidence_threshold": settings.confidence_threshold,
            "threshold_percent": int(round(settings.confidence_threshold * 100)),
            "auto_organize": settings.auto_organize,
            "rename_files": settings.rename_files,
            "safe_mode_undo": settings.safe_mode_undo,
            "ocr_enabled": settings.ocr_enabled,
            "low_confidence_action": settings.low_confidence_action,
        }

    @app.patch("/api/settings")
    def update_settings(body: SettingsUpdateRequest) -> dict[str, Any]:
        if body.watched_dir is not None:
            settings.watched_dir = Path(body.watched_dir).expanduser().resolve()
            active_pipeline.watched_dir = settings.watched_dir
        if body.organized_dir is not None:
            settings.organized_dir = Path(body.organized_dir).expanduser().resolve()
            active_pipeline.organized_dir = settings.organized_dir
        if body.ollama_host is not None:
            settings.ollama_host = body.ollama_host
        if body.gemma_model is not None:
            settings.gemma_model = body.gemma_model
        if body.confidence_threshold is not None:
            settings.confidence_threshold = max(0.0, min(1.0, body.confidence_threshold))
        elif body.threshold_percent is not None:
            settings.confidence_threshold = max(0.0, min(1.0, body.threshold_percent / 100.0))
        if body.auto_organize is not None:
            settings.auto_organize = body.auto_organize
        if body.rename_files is not None:
            settings.rename_files = body.rename_files
        if body.safe_mode_undo is not None:
            settings.safe_mode_undo = body.safe_mode_undo
        if body.ocr_enabled is not None:
            settings.ocr_enabled = body.ocr_enabled
        if body.low_confidence_action is not None:
            settings.low_confidence_action = body.low_confidence_action
        return get_settings()

    @app.post("/api/scan")
    def trigger_scan(body: ScanRequest | None = None) -> dict[str, Any]:
        req = body or ScanRequest()
        if req.path:
            target = Path(req.path).expanduser().resolve()
            if not target.exists():
                raise HTTPException(status_code=404, detail=f"Path not found: {target}")
            if target.is_file():
                rec = active_pipeline.process_file(target)
                return {"processed": [rec] if rec else [], "count": 1 if rec else 0}
            records = active_pipeline.scan_directory(target)
            return {"processed": records, "count": len(records)}

        records = active_pipeline.scan_directory()
        return {"processed": records, "count": len(records)}

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket) -> None:
        await websocket.accept()
        ws_clients.add(websocket)
        try:
            await websocket.send_json({"event": "connected", "data": {"service": "FileMind"}})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_clients.discard(websocket)
        except Exception:
            ws_clients.discard(websocket)

    return app


app = create_app(enable_watcher=False)
