# AutoGuard AI — API reference

Base URL: `http://127.0.0.1:8000`

All responses are JSON unless noted. Errors use `{"detail": "..."}` with a 4xx/5xx status.

## Health

### `GET /api/health`

```json
{
  "status": "ready",
  "app": "AutoGuard AI",
  "version": "1.0.0",
  "database": "C:\\...\\data\\autoguard.db",
  "weights": "C:\\...\\models\\plate_detector.pt",
  "pipeline_ready": true,
  "plates_stored": 50,
  "features": {
    "demo": true,
    "llm": false,
    "llm_provider": "local",
    "llm_model": ""
  }
}
```

`status` is `waiting_for_detector` when the weights file is missing. The review queue, archive, intelligence and assistant views still work; only `/api/analyze` returns 503.

## Analysis

### `POST /api/analyze`

Multipart form field: `image` (JPG, PNG, WEBP or BMP; max 12 MB).

Query parameters:

| Name | Default | Meaning |
|---|---|---|
| `save` | `true` | Persist the analysis and plate rows. |
| `source` | `upload` | Fixed to upload for this endpoint. |

Response (abridged):

```json
{
  "filename": "car.jpg",
  "processing_ms": 1840.2,
  "saved": true,
  "analysis_id": 51,
  "annotated_image": "data:image/jpeg;base64,...",
  "annotated_preview": "data:image/jpeg;base64,...",
  "detection": {"confidence": 0.15, "imgsz": 1280, "raw_boxes": 3, "merged_boxes": 2, "merged_pairs": 1},
  "plates": [
    {
      "plate_id": 88,
      "box_xyxy": [120, 140, 520, 220],
      "crop_box_xyxy": [96, 135, 544, 225],
      "detector_confidence": 0.91,
      "merged_detections": 2,
      "edge_touching": false,
      "ocr_prediction": "TS09AB1234",
      "ocr_engine_score": 0.91,
      "original_prediction": "TS09AB12?4",
      "original_ocr_score": 0.42,
      "common_format_match": true,
      "review_status": "candidate_passed_validation_gate",
      "quality_flags": ["possible blur", "low contrast"],
      "brightness": 74.0,
      "contrast": 31.0,
      "blur_score": 41.0,
      "retry_attempted": true,
      "retry_reasons": ["possible blur", "low contrast", "low OCR engine score"],
      "selection_reason": "selected standard-format alternative: score gain at least 0.25",
      "selected_method": "enhanced + upscaled",
      "recovery_outcome": "recovered",
      "recovery_delta": 0.49,
      "candidates": [
        {"text": "TS09AB12?4", "score": 0.42, "method": "upscaled original"},
        {"text": "TS09AB1234", "score": 0.91, "method": "enhanced + upscaled"}
      ],
      "observations": ["Recovery retry triggered by: possible blur, low contrast."],
      "image_preview": "data:image/jpeg;base64,...",
      "crop_preview": "data:image/jpeg;base64,...",
      "enhanced_preview": "data:image/jpeg;base64,...",
      "rectified_preview": "data:image/jpeg;base64,..."
    }
  ]
}
```

Status codes: `200` success, `400` undecodable, `413` too large, `415` wrong type, `422` invalid form, `503` missing ML stack/weights.

## Analytics

### `GET /api/analytics/summary`

Query: `days` (1–365, default 30), `include_demo` (bool, default true).

```json
{
  "days": 30,
  "since": "2026-10-13T18:30:00+00:00",
  "total_analyses": 50,
  "total_plates": 50,
  "passed": 28,
  "review": 22,
  "unreadable": 0,
  "retries": 19,
  "recovered": 16,
  "degraded": 0,
  "verified": 12,
  "corrected": 3,
  "low_confidence": 19,
  "avg_ocr_score": 0.7332,
  "avg_detector_confidence": 0.7749,
  "avg_processing_ms": 930.9,
  "pass_rate": 0.56,
  "review_rate": 0.44,
  "recovery_rate": 0.8421,
  "correction_rate": 0.25,
  "today_plates": 2,
  "today_passed": 1,
  "previous_plates": 0,
  "period_delta_pct": null,
  "demo_analyses": 50,
  "upload_analyses": 0,
  "last_seen": "2026-11-12T16:04:48+00:00"
}
```

### `GET /api/analytics/timeseries`

Query: `days` (1–90, default 14), `include_demo`.

```json
{
  "items": [
    {"date": "2026-10-30", "label": "30 Oct", "analyses": 2, "plates": 2, "passed": 1, "review": 1, "recovered": 1}
  ]
}
```

### `GET /api/analytics/breakdown`

Query: `days`, `include_demo`.

```json
{
  "failures": [{"reason": "Overexposure", "count": 18, "share": 0.2812}],
  "recovery": [{"outcome": "recovered", "label": "Recovered", "count": 15, "share": 0.3659}],
  "methods": [{"method": "enhanced + upscaled", "count": 21, "share": 0.42}]
}
```

### `GET /api/analytics/benchmark`

Returns the measured OCR test summary and detector validation metrics from `reports/ocr_final_test_v2.json`, `reports/gate_curve.json`, `reports/final_evaluation.json`, the frame-vote reports and `runs/detect/plate_yolov8n/results.csv`.

```json
{
  "ocr": {
    "samples": 165,
    "exact_match": 0.6848,
    "exact_match_ci95": [0.6104, 0.7508],
    "cer": 0.0972,
    "similarity": 0.9028,
    "baseline_exact_match": 0.5212,
    "baseline_cer": 0.1868,
    "gate_coverage": 0.5818,
    "gate_selective_accuracy": 0.9271,
    "gate_threshold": 0.81,
    "workload": {"auto_pass_per_100": 58.2, "review_per_100": 41.8, "residual_errors_per_100": 4.24},
    "rescue": {
      "enabled": true,
      "rule": "Keep a common-format base reading with engine score >= 0.55; otherwise add direct-CRNN, rotated and per-row candidates.",
      "trusted_samples": 103
    },
    "risk_control": {
      "threshold": 0.81,
      "target_error": 0.08,
      "validation_coverage": 0.6242,
      "validation_selective_accuracy": 0.9223,
      "test_coverage": 0.5818,
      "test_selective_accuracy": 0.9271,
      "test_error": 0.0729,
      "risk_target_met_on_test": true
    }
  },
  "detector": {"epoch": 30, "precision": 0.9868, "recall": 1.0, "map50": 0.9931, "map50_95": 0.8399, "split": "validation"},
  "external_iurs": {"samples": 110, "exact_match": 0.8636, "exact_match_ci95": [0.7871, 0.9156], "cer": 0.0172, "similarity": 0.9828, "gate_coverage": 0.6636, "gate_selective_accuracy": 0.9452, "workload": {"auto_pass_per_100": 66.4, "review_per_100": 33.6, "residual_errors_per_100": 3.64}},
  "composition": {"samples": 165, "unique_plates": 97, "plate_macro_exact_match": 0.6477, "plate_macro_ci95": [0.551, 0.7365], "dominant_plate": "MH02DS9365", "dominant_plate_crops": 34, "dominant_share_of_test": 0.2061, "frame_exact_match_without_dominant": 0.6336},
  "frame_vote": {"all_plates": {"first_frame": {"rate": 0.6495}, "majority_vote": {"rate": 0.6598}, "any_crop": {"rate": 0.6701}}, "multi_frame_plates": {"plates": 18, "frames": 86}, "iurs": {"all_plates": {"majority_vote": {"rate": 0.8831}}}},
  "note": "Internal development estimate..."
}
```

### `GET /api/analytics/gate-curve`

Returns `reports/gate_curve.json`: the threshold sweep used to calibrate the review gate. The threshold is chosen on validation only, frozen, and replayed; both curves are returned for inspection and for the Intelligence view.

```json
{
  "target_error": 0.08,
  "target_accuracy": 0.92,
  "validation_samples": 165,
  "test_samples": 165,
  "recommended": {"threshold": 0.81, "coverage": 0.6242, "selective_accuracy": 0.9223, "selective_error": 0.0777, "eligible": 103},
  "test_at_recommended": {"threshold": 0.81, "coverage": 0.5818, "selective_accuracy": 0.9271, "selective_error": 0.0729, "eligible": 96},
  "risk_target_met_on_validation": true,
  "risk_target_met_on_test": true,
  "threshold_pinned": true,
  "validation_curve": [{"threshold": 0.5, "coverage": 0.8, "selective_accuracy": 0.8788, "selective_error": 0.1212, "eligible": 132}],
  "test_curve": [{"threshold": 0.5, "coverage": 0.7455, "selective_accuracy": 0.8618, "selective_error": 0.1382, "eligible": 123}],
  "prediction_column": "margin_0.25_prediction",
  "score_column": "margin_0.25_score"
}
```

`404` if the calibration has not been generated; run `python scripts/calibrate_gate.py`.

### `GET /api/analytics/export`

Query: `days`, `include_demo`. Returns `text/csv` with a UTF-8 BOM and columns: `id, created_at, filename, source, ocr_text, verified_text, verification_status, review_status, recovery_outcome, detector_confidence, ocr_score, original_text, original_score, common_format, quality_flags, retry_attempted, retry_reasons, selection_reason, selected_method, brightness, contrast, blur_score, candidates, observations, ground_truth`.

## Plates

### `GET /api/plates`

Query: `status` (`all`, `review`, `recovered`, `passed`, `failed`, `low_confidence`, `corrected`, `unverified`), `q`, `days`, `limit` (1–100), `offset`, `include_demo`.

```json
{
  "items": [{
    "id": 12,
    "analysis_id": 8,
    "plate_index": 1,
    "created_at": "2026-11-12T09:40:16+00:00",
    "ocr_text": "TS09AB1234",
    "display_text": "TS09AB1234",
    "original_text": "TS09AB12?4",
    "ocr_score": 0.91,
    "original_score": 0.42,
    "detector_confidence": 0.88,
    "review_status": "candidate_passed_validation_gate",
    "verification_status": "unreviewed",
    "recovery_outcome": "recovered",
    "recovery_delta": 0.49,
    "quality_flags": ["possible blur"],
    "failure_reasons": ["possible blur"],
    "retry_attempted": true,
    "crop_preview": "data:image/jpeg;base64,...",
    "filename": "car.jpg",
    "source": "upload",
    "is_demo": false
  }],
  "total": 1,
  "limit": 20,
  "offset": 0,
  "has_more": false
}
```

### `GET /api/plates/{id}`

Returns one plate record; `404` if missing.

### `POST /api/plates/{id}/verify`

```json
{"verified_text": "TS09AB1234", "status": "corrected"}
```

`status` is `confirmed`, `corrected` or `rejected`. `verified_text` is normalized to uppercase letters/digits. Required unless rejecting. Returns the updated record; `422` for invalid input, `404` if missing.

### `GET /api/plates/{id}/explain`

Returns a grounded explanation:

```json
{
  "plate": {...},
  "reply": "**Plate #12 — TS09AB1234** ...",
  "citations": [{"title": "Failure taxonomy", "section": "Motion and focus blur", "snippet": "...", "score": 4.2}],
  "intent": "explain_plate",
  "mode": "local"
}
```

## Assistant

### `GET /api/assistant/status`

```json
{
  "mode": "local",
  "llm": {"available": false, "provider": "local", "model": "", "mode": "local"},
  "knowledge_chunks": 39,
  "suggestions": ["How many vehicles were analysed today?", "..."],
  "auto_connect": {"enabled": true, "url": "http://127.0.0.1:11434"}
}
```

With `auto_connect.enabled`, the server probes a loopback Ollama server (at most once every 15 s) and attaches automatically when at least one model is installed. A manual disconnect turns `enabled` to `false` until a manual connect.

### `GET /api/assistant/suggestions`

```json
{"suggestions": ["..."]}
```

### `GET /api/assistant/detect`

Probes a local Ollama server. Query: `url` (default `http://127.0.0.1:11434`). Only loopback hosts are accepted; a remote host returns `422`.

```json
{"reachable": true, "url": "http://127.0.0.1:11434", "models": ["llama3.2:3b"], "status": {"mode": "local", "llm": {"available": false, "provider": "local", "model": "", "mode": "local"}, "knowledge_chunks": 39, "suggestions": ["..."]}}
```

`reachable` means the server answered the `/api/tags` probe. It can be `true` with an empty `models` list when Ollama is running but no model has been pulled; the UI then shows the `ollama pull` command instead of claiming detection failed. `reachable: false` means nothing answered, which is a normal offline state, not an error.

### `POST /api/assistant/llm`

Connects or disconnects the runtime LLM.

```json
{"provider": "ollama", "url": "http://127.0.0.1:11434", "model": "llama3.2:3b"}
```

`provider`: `ollama` or `off`. With `off`, the client is reset to the deterministic local mode, auto-connect is paused, and the response is `{"connected": false, "status": {...}, "auto_connect": {"enabled": false, ...}}`. With `ollama`, the URL must be loopback, at least one model must be installed, and `model` must be present (an empty value selects the first installed model). Returns `{"connected": true, "url": "...", "model": "...", "status": {...}, "auto_connect": {"enabled": true, ...}}`. Errors: `503` if Ollama is unreachable **or reachable with zero installed models** (the detail carries the `ollama pull` hint), `404` if the requested model is not installed, `422` for a non-loopback or malformed URL.

### `POST /api/assistant/chat`

```json
{"message": "Show me the plates that need manual review.", "session_id": "optional-existing-id"}
```

```json
{
  "session_id": "9f2c...",
  "reply": "I found **5 plate reading(s) needing manual review** ...",
  "intent": "review",
  "mode": "local",
  "citations": [],
  "plates": [{"id": 12, "text": "TS09AB1234", "score": 0.91, "filename": "car.jpg", "review_status": "needs_manual_review", "verification_status": "unreviewed", "recovery_outcome": "recovered", "created_at": "..."}],
  "metrics": {},
  "suggestions": ["..."],
  "llm_error": "",
  "created_at": "2026-11-12T20:15:00+05:30"
}
```

`mode`: `local`, `llm` or `local_fallback`. In `llm` mode the model receives the full retrieved documentation sections (not truncated snippets) plus the deterministic draft, and answers the question directly; `llm_error` is filled only for `local_fallback`. A model call is allowed up to `AUTOGUARD_LLM_TIMEOUT` seconds (default 90). `intent` is `llm_mode` for questions about the assistant's own model/grounding.

### `GET /api/assistant/session/{id}`

```json
{
  "session_id": "9f2c...",
  "messages": [
    {"id": 1, "role": "user", "content": "...", "meta": {}, "created_at": "..."},
    {"id": 2, "role": "assistant", "content": "...", "meta": {"intent": "stats", "mode": "local", "citations": [], "plates": [], "metrics": {}, "suggestions": []}, "created_at": "..."}
  ]
}
```

## Demo

### `POST /api/demo/seed`

```json
{"days": 21, "confirm": true}
```

Returns `{"seeded": 41, "message": "..."}`. `403` if `AUTOGUARD_DEMO=0`; `400` without `confirm=true`; `200` with `seeded: 0` if demo rows already exist.

### `DELETE /api/demo`

Returns `{"cleared": 41}`.

## Error handling

| Status | Meaning |
|---|---|
| 400 | Bad request / undecodable image / missing confirmation |
| 403 | Demo endpoints disabled |
| 404 | Plate, session or resource not found |
| 413 | Upload too large |
| 415 | Unsupported image type |
| 422 | Validation error (message, verification payload) |
| 503 | ML stack or detector weights unavailable |
