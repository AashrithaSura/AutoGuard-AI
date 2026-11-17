# Project Structure

This is the maintained layout of the AutoGuard AI project.

```text
self-healing-anpr/
├─ api/                     FastAPI application and HTTP endpoints
├─ src/anpr/                Core Python package: detector, OCR, recovery, database, assistant
├─ web/                     Console shell, single design-system stylesheet and SPA logic
├─ models/                  Runtime model weights only
├─ models/attic/            Pre-v2 OCR weights kept for rollback
├─ data/                    Prepared datasets and restoration data
├─ reports/                 Evaluation JSON/CSV, gate_curve.json and reports
├─ runs/                    Detector training summary read by the API (results.csv)
├─ scripts/                 Dataset builders, calibration, training helpers, benchmarks
├─ tests/                   Automated tests
├─ docs/                    Reports, guides, API and viva material
├─ docs/AutoGuard_AI_Capstone_Report.pdf   Printable report built from CAPSTONE_REPORT.md
├─ attic/                   Superseded artifacts kept for traceability only
├─ requirements.txt         Runtime dependencies
├─ requirements-dev.txt     Development/test dependencies
├─ run.ps1                  Start the local API and web application
├─ setup.ps1                Create the environment and install dependencies
├─ train_detector.py        Detector training entry point
├─ train_ocr.py             OCR fine-tuning entry point
├─ evaluate_detector.py     Detector evaluation entry point
└─ evaluate_ocr_crops.py    OCR evaluation entry point
```

## Front end

| Path | Purpose |
|---|---|
| `web/index.html` | Console shell: gradient top navigation, page header (palette button, clock, theme, new scan), and modal/drawer/palette/toast roots. |
| `web/console.css` | The only stylesheet. Light and `[data-theme="dark"]` tokens, nav shell, scan desk, review desk, ledger, intelligence, restoration lab, assistant, overlays and responsive rules. |
| `web/app.js` | Hash-routed SPA: scan desk (`#/scan`), review queue (`#/review`), plate archive (`#/archive`), intelligence (`#/intel`, with `#/intel/gate`, `#/intel/restore`, `#/intel/data`), assistant (`#/assistant`), command palette, dossier drawer, compare slider, theme, toasts. |

Legacy `styles.css`, `theme.css`, `redesign.css` and `studio.css` were replaced by `console.css` and are archived in `attic/pre_v3_20261117/web_legacy_css/`.

## Runtime files

| Path | Purpose |
|---|---|
| `models/plate_detector.pt` | Production YOLOv8n plate detector. |
| `models/plate_ocr.pth` | Fine-tuned EasyOCR recognition checkpoint. |
| `models/attic/plate_ocr_pre_v2.pth` | Previous OCR checkpoint, kept for rollback. |
| `models/RealESRGAN_x4plus.pth` | Experimental restoration model. |
| `models/refine_net_l1.pth` | Experimental plate refiner. |
| `models/yolov8n.pt` | Base YOLO weights for retraining. |
| `data/autoguard.db` | Local SQLite database created at runtime. |
| `data/prepared_corrected/` | Corrected detector and OCR dataset with the held-out splits. |
| `data/iurs_plates/` | Plate crops rebuilt from the IURS character set for the combined retrain. |
| `data/combined_ocr/` | Combined OCR manifests used to train the shipped recogniser. |
| `reports/gate_curve.json` | Validation-selected gate threshold and both risk curves. |

## Archive

`attic/` holds superseded artifacts. Nothing in `attic/` is imported by the application.- `pre_v3_20261117/` — pre-redesign UI snapshot with `RESTORE.md`.
- `pre_v2_20261117/` — snapshot before the combined-data OCR retrain.
- `pre_autoguard_20261112/` — snapshot before the current web app.
- `refine_net_l1_before_retrain.pth` — previous plate-refiner checkpoint.
- `cleanup_20261118/` — detector training plots, `runs/eval/` outputs and the old IURS eval log, archived out of the runtime tree. Safe to delete once the shipped metrics are trusted.

Both rollback paths are deliberate: restore the UI from `attic/pre_v3_20261117/` and the previous recogniser from `models/attic/plate_ocr_pre_v2.pth`.

## Report PDF

`docs/AutoGuard_AI_Capstone_Report.pdf` is generated from `docs/CAPSTONE_REPORT.md`:

```powershell
.\.venv\Scripts\python.exe scripts\build_report_pdf.py
node scripts\print_report_pdf.mjs
```

The first step writes styled HTML to the system temp folder; the second prints it with the local Chrome. The repository keeps only the Markdown source and the PDF.

## Cleanup rules

Keep in the project root only:

- application entry points
- dependency and setup files
- README

Move one-off analysis to `scripts/`, documentation to `docs/`, evaluations to `reports/`, and superseded work to `attic/`.

Do not commit:

- `.venv/`
- `__pycache__/`
- `data/autoguard.db`
- uploaded images
- browser profiles and screenshots
- temporary CSV/JSON output

## Start

```powershell
.\run.ps1
```

Open <http://127.0.0.1:8000>.
