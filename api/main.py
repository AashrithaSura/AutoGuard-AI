"""FastAPI application for AutoGuard AI.

The API deliberately keeps the ML pipeline lazy: dashboard, recovery and
assistant endpoints should work even when the optional ML stack is not
installed.  This is also what lets the repository's service tests run in a
minimal environment.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from src.anpr.assistant import Assistant
from src.anpr.benchmark import benchmark_summary
from src.anpr.config import (
    APP_NAME,
    APP_VERSION,
    DB_PATH,
    DEMO_ENABLED,
    MAX_UPLOAD_BYTES,
    MODEL_DIR,
    OLLAMA_MODEL,
    OLLAMA_URL,
    REPORT_DIR,
    WEB_DIR,
    feature_flags,
)
from src.anpr.db import Database, derive_recovery_outcome
from src.anpr.restoration import RestorationEngine

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

_pipeline = None
_db: Database | None = None
_assistant: Assistant | None = None
_restoration: RestorationEngine | None = None

# The assistant attaches to a loopback Ollama server automatically. A manual
# disconnect opts out until the user connects again; the probe is cached so
# status polling stays cheap.
_LLM_AUTO_URL = OLLAMA_URL or "http://127.0.0.1:11434"
_LLM_AUTO_TTL = 15.0
_llm_auto = {"opt_out": False, "checked_at": 0.0, "reachable": None, "models": []}


def _auto_attach_ollama(assistant: Assistant) -> None:
    if assistant.llm.available or _llm_auto["opt_out"]:
        return
    now = time.time()
    if now - _llm_auto["checked_at"] < _LLM_AUTO_TTL:
        return
    _llm_auto["checked_at"] = now
    try:
        base = _local_ollama_base(_LLM_AUTO_URL)
    except HTTPException:
        return
    reachable, models = _ollama_probe(base, timeout=0.6)
    _llm_auto["reachable"] = reachable
    _llm_auto["models"] = models
    if not models:
        return
    from src.anpr.llm import LLMClient

    model = OLLAMA_MODEL if OLLAMA_MODEL in models else models[0]
    assistant.llm = LLMClient(ollama_url=base, ollama_model=model)


def _auto_connect_state() -> dict:
    return {
        "enabled": not _llm_auto["opt_out"],
        "url": _LLM_AUTO_URL,
        "reachable": _llm_auto["reachable"],
        "models": _llm_auto["models"],
    }


def _full_frame_preview(data_url: str, max_width: int = 1280) -> str:
    """Return a smaller JPEG data URL for the full annotated frame."""
    if not data_url or "," not in data_url:
        return ""
    try:
        import base64

        import cv2
        import numpy as np

        header, encoded = data_url.split(",", 1)
        image = cv2.imdecode(np.frombuffer(base64.b64decode(encoded), np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return ""
        height, width = image.shape[:2]
        if width > max_width:
            scale = max_width / width
            image = cv2.resize(image, (max_width, int(height * scale)), interpolation=cv2.INTER_AREA)
        ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not ok:
            return ""
        encoded = base64.b64encode(buffer).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return ""


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(DB_PATH)
    return _db


def get_assistant() -> Assistant:
    global _assistant
    if _assistant is None:
        _assistant = Assistant(get_db())
    return _assistant


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        weights = MODEL_DIR / "plate_detector.pt"
        if not weights.is_file():
            raise FileNotFoundError(f"Detector weights not found: {weights}")
        from src.anpr.pipeline import SelfHealingANPR

        _pipeline = SelfHealingANPR(weights, gpu=False)
    return _pipeline


def get_restoration() -> RestorationEngine:
    global _restoration
    if _restoration is None:
        _restoration = RestorationEngine(MODEL_DIR, device="cpu")
    return _restoration


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1200)
    session_id: str | None = None


class VerifyRequest(BaseModel):
    verified_text: str = Field(default="", max_length=20)
    status: Literal["confirmed", "corrected", "rejected"] = "corrected"


class DemoRequest(BaseModel):
    days: int = Field(default=21, ge=1, le=90)
    confirm: bool = False


class LLMConnectRequest(BaseModel):
    provider: Literal["ollama", "off"] = "ollama"
    url: str = "http://127.0.0.1:11434"
    model: str = ""


def _local_ollama_base(url: str) -> str:
    """Accept only loopback Ollama endpoints so the UI cannot be used to proxy arbitrary hosts."""
    from urllib.parse import urlparse

    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=422, detail="Ollama URL must start with http:// or https://.")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(status_code=422, detail="Only local Ollama endpoints are allowed. Use AUTOGUARD_OLLAMA_URL for remote hosts.")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise HTTPException(status_code=422, detail="Use the Ollama base URL without a path.")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def _ollama_probe(base: str, timeout: float = 2.0) -> tuple[bool, list[str]]:
    """Return (server_answered, installed_models).

    A running server with no models is reachable but cannot be attached, which
    the UI reports separately from an unreachable server.
    """
    import urllib.request

    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = [
            str(item.get("name") or "").strip()
            for item in payload.get("models") or []
            if str(item.get("name") or "").strip()
        ]
    except Exception:
        return False, []
    return True, models


def _ollama_models(base: str, timeout: float = 2.0) -> list[str]:
    return _ollama_probe(base, timeout)[1]


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/api/health")
def health():
    db = get_db()
    summary = db.summary(days=30)
    pipeline_ready = (MODEL_DIR / "plate_detector.pt").is_file()
    features = feature_flags()
    attached = _assistant.llm.status() if _assistant is not None else None
    if attached and attached["available"]:
        features.update(
            llm=True,
            llm_provider=attached["provider"],
            llm_model=attached["model"],
        )
    return {
        "status": "ready" if pipeline_ready else "waiting_for_detector",
        "app": APP_NAME,
        "version": APP_VERSION,
        "database": str(DB_PATH),
        "weights": str(MODEL_DIR / "plate_detector.pt"),
        "pipeline_ready": pipeline_ready,
        "plates_stored": summary["total_plates"],
        "features": features,
    }


@app.post("/api/analyze")
async def analyze(
    image: UploadFile = File(...),
    save: bool = Query(default=True),
    source: Literal["upload"] = Query(default="upload"),
):
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
    allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    suffix = Path(image.filename or "").suffix.lower()
    if image.content_type not in allowed_types and suffix not in allowed_suffixes:
        raise HTTPException(status_code=415, detail="Upload a JPG, PNG, WEBP, or BMP image.")
    data = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Image must be {MAX_UPLOAD_BYTES // (1024 * 1024)} MB or smaller.")
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=503,
            detail="OpenCV is not installed. Run: pip install -r requirements.txt",
        ) from exc
    decoded = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise HTTPException(status_code=400, detail="Could not decode the uploaded image.")
    try:
        pipeline = get_pipeline()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    started = time.perf_counter()
    try:
        result = pipeline.process(decoded)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    elapsed = round((time.perf_counter() - started) * 1000, 1)
    filename = Path(image.filename or "upload").name
    result["filename"] = filename
    result["processing_ms"] = elapsed
    result["saved"] = False
    result["annotated_preview"] = _full_frame_preview(result.get("annotated_image", ""))
    for plate in result.get("plates", []):
        plate["image_preview"] = result["annotated_preview"]
        plate["recovery_outcome"] = derive_recovery_outcome(plate)
        plate["recovery_delta"] = round(
            float(plate.get("ocr_engine_score") or 0) - float(plate.get("original_ocr_score") or 0),
            4,
        )
    if save:
        height, width = decoded.shape[:2]
        saved = get_db().save_analysis(
            result,
            filename,
            source=source,
            processing_ms=elapsed,
            image_sha256=hashlib.sha256(data).hexdigest(),
            width=width,
            height=height,
        )
        result["analysis_id"] = saved["analysis_id"]
        result["saved"] = True
        for plate, plate_id in zip(result.get("plates", []), saved["plate_ids"]):
            plate["plate_id"] = plate_id
    return JSONResponse(result)


@app.post("/api/restore")
async def restore(image: UploadFile = File(...)):
    """Run the Restoration Lab: Bicubic, Real-ESRGAN and optional RefineNet.

    This endpoint is intentionally separate from /api/analyze. Restoration is
    a lab feature until it proves an OCR gain on real validation crops.
    """
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
    suffix = Path(image.filename or "").suffix.lower()
    if image.content_type not in allowed_types and suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        raise HTTPException(status_code=415, detail="Upload a JPG, PNG, WEBP, or BMP image.")
    data = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 12 MB or smaller.")
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="OpenCV is not installed.") from exc
    decoded = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise HTTPException(status_code=400, detail="Could not decode the uploaded image.")
    try:
        engine = get_restoration()
        if not engine.ready:
            raise HTTPException(status_code=503, detail="Real-ESRGAN weights are missing.")
        result = engine.restore_all(decoded)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    images = result.pop("images")
    ocr = {}
    try:
        pipeline = get_pipeline()
        for name, picture in images.items():
            candidate = pipeline._read(picture, name)
            ocr[name] = {"text": candidate.text, "score": round(candidate.score, 4)}
    except Exception as exc:  # OCR failure should not hide the restored images
        ocr = {"error": str(exc)[:200]}
    result["ocr"] = ocr
    return JSONResponse(result)


@app.get("/api/analytics/summary")
def analytics_summary(days: int = Query(default=30, ge=1, le=365), include_demo: bool = True):
    return get_db().summary(days=days, include_demo=include_demo)


@app.get("/api/analytics/timeseries")
def analytics_timeseries(days: int = Query(default=14, ge=1, le=90), include_demo: bool = True):
    return {"items": get_db().timeseries(days=days, include_demo=include_demo)}


@app.get("/api/analytics/breakdown")
def analytics_breakdown(days: int = Query(default=30, ge=1, le=365), include_demo: bool = True):
    db = get_db()
    return {
        "failures": db.failure_breakdown(days=days, include_demo=include_demo),
        "recovery": db.recovery_breakdown(days=days, include_demo=include_demo),
        "methods": db.method_breakdown(days=days, include_demo=include_demo),
    }


@app.get("/api/analytics/benchmark")
def analytics_benchmark():
    return benchmark_summary()


@app.get("/api/analytics/gate-curve")
def analytics_gate_curve():
    path = REPORT_DIR / "gate_curve.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Gate calibration not generated. Run: python scripts/calibrate_gate.py")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Could not read gate calibration: {exc}") from exc


@app.get("/api/analytics/export")
def analytics_export(days: int = Query(default=30, ge=1, le=365), include_demo: bool = True):
    csv_text = get_db().export_csv(days=days, include_demo=include_demo)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="autoguard_plates.csv"'},
    )


@app.get("/api/plates")
def list_plates(
    status: str = Query(default="all"),
    q: str = Query(default="", max_length=80),
    days: int | None = Query(default=None, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_demo: bool = True,
):
    return get_db().list_plates(
        status=status,
        query=q,
        days=days,
        limit=limit,
        offset=offset,
        include_demo=include_demo,
    )


@app.get("/api/plates/{plate_id}")
def get_plate(plate_id: int):
    plate = get_db().get_plate(plate_id)
    if not plate:
        raise HTTPException(status_code=404, detail="Plate not found.")
    return plate


@app.post("/api/plates/{plate_id}/verify")
def verify_plate(plate_id: int, request: VerifyRequest):
    try:
        plate = get_db().verify_plate(plate_id, request.verified_text, request.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not plate:
        raise HTTPException(status_code=404, detail="Plate not found.")
    return plate


@app.post("/api/plates/{plate_id}/reopen")
def reopen_plate(plate_id: int):
    plate = get_db().clear_verification(plate_id)
    if not plate:
        raise HTTPException(status_code=404, detail="Plate not found.")
    return plate


@app.delete("/api/plates/{plate_id}")
def delete_plate(plate_id: int):
    if not get_db().delete_plate(plate_id):
        raise HTTPException(status_code=404, detail="Plate not found.")
    return {"deleted": plate_id}


@app.get("/api/plates/{plate_id}/explain")
def explain_plate(plate_id: int):
    try:
        return get_assistant().explain_plate(plate_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/assistant/status")
def assistant_status():
    assistant = get_assistant()
    _auto_attach_ollama(assistant)
    payload = assistant.status()
    payload["auto_connect"] = _auto_connect_state()
    return payload


@app.get("/api/assistant/detect")
def assistant_detect(url: str = Query(default="http://127.0.0.1:11434")):
    base = _local_ollama_base(url)
    reachable, models = _ollama_probe(base)
    status = get_assistant().status()
    status["auto_connect"] = _auto_connect_state()
    return {
        "reachable": reachable,
        "url": base,
        "models": models,
        "status": status,
    }


@app.post("/api/assistant/llm")
def assistant_connect(request: LLMConnectRequest):
    from src.anpr.llm import LLMClient

    assistant = get_assistant()
    if request.provider == "off":
        assistant.llm = LLMClient()
        _llm_auto["opt_out"] = True
        _llm_auto["reachable"] = None
        _llm_auto["models"] = []
        return {"connected": False, "status": assistant.status(), "auto_connect": _auto_connect_state()}
    base = _local_ollama_base(request.url)
    reachable, models = _ollama_probe(base)
    if not reachable:
        raise HTTPException(status_code=503, detail=f"Could not reach an Ollama server at {base}. Start Ollama and try again.")
    if not models:
        raise HTTPException(
            status_code=503,
            detail=f"Ollama is running at {base}, but no models are installed. Run: ollama pull llama3.2",
        )
    model = request.model.strip()
    if not model:
        model = models[0]
    elif model not in models:
        raise HTTPException(status_code=404, detail=f"Model '{model}' is not installed. Available: {', '.join(models[:8])}")
    assistant.llm = LLMClient(ollama_url=base, ollama_model=model)
    _llm_auto["opt_out"] = False
    _llm_auto["checked_at"] = 0.0
    _llm_auto["reachable"] = True
    _llm_auto["models"] = models
    return {
        "connected": True,
        "url": base,
        "model": model,
        "status": assistant.status(),
        "auto_connect": _auto_connect_state(),
    }


@app.get("/api/assistant/suggestions")
def assistant_suggestions():
    return {"suggestions": get_assistant().status()["suggestions"]}


@app.post("/api/assistant/chat")
def assistant_chat(request: ChatRequest):
    try:
        return get_assistant().chat(request.message, request.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/assistant/session/{session_id}")
def assistant_session(session_id: str):
    messages = get_db().get_messages(session_id)
    return {"session_id": session_id, "messages": messages}


@app.post("/api/demo/seed")
def demo_seed(request: DemoRequest):
    if not DEMO_ENABLED:
        raise HTTPException(status_code=403, detail="Demo seeding is disabled.")
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Send confirm=true to seed synthetic demo rows.")
    db = get_db()
    existing = db.summary(days=365)["demo_analyses"]
    if existing:
        return {"seeded": 0, "message": f"{existing} demo analyses already exist. Clear them first."}
    count = db.seed_demo(days=request.days)
    return {"seeded": count, "message": f"Seeded {count} clearly-labelled demo analyses."}


@app.delete("/api/demo")
def demo_clear():
    if not DEMO_ENABLED:
        raise HTTPException(status_code=403, detail="Demo management is disabled.")
    count = get_db().clear_demo()
    return {"cleared": count}


@app.get("/api/export/observations.csv")
def export_observations(days: int = Query(default=30, ge=1, le=365), include_demo: bool = True):
    return analytics_export(days=days, include_demo=include_demo)
