# AutoGuard AI — Training Playbook

Everything here runs locally. **Do not spend the $0.93 API credit on training.**

## Status

| Priority | Work | Status |
|---|---|---|
| 1 | Restoration experiment | Done — candidate rejected; `models/refine_net_l1.pth` kept |
| 2 | UI/recovery bugs | Done |
| 3 | Character-detector pilot on IURS | Done — rejected (mAP50 0.05) |
| 4 | Real text-labelled plate crops + 4-corner rectification | Open — highest chance of improving 68.48% exact match |
| 5 | Fresh untouched test set | Open |
| 6 | Demo pack | Done |

The guides below are kept so any of these can be rerun. The derived datasets
(`data/restoration/`, `data/iurs/`) are not shipped; recreate them first.

## Priority 1 — Restoration training

### Files

- Training script: `scripts/train_refiner_fast.py`
- Triplet builder: `scripts/build_restoration_split.py --split train|val|test`
- Pairs manifest: `data/restoration/manifest.csv` (build it before training; not shipped)
- Current validated model: `models/refine_net_l1.pth`
- Old backup: `attic/refine_net_l1_before_retrain.pth`

The script now trains to a **candidate** file by default. It cannot overwrite the validated model.

### Commands

```powershell
cd C:\Users\suraa\Desktop\ANPR2\self-healing-anpr

.\.venv\Scripts\python.exe scripts\train_refiner_fast.py `
  --epochs 8 `
  --batch 32 `
  --lr 0.00005 `
  --source models\refine_net_l1.pth `
  --output models\refine_net_candidate.pth
```

Outputs:

- `models/refine_net_candidate.pth` — best candidate checkpoint
- `reports/restoration_training_history.json` — epoch losses

### Benchmark the candidate

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_restoration.py `
  --checkpoint models\refine_net_candidate.pth `
  --output reports\restoration_benchmark_candidate.json
```

Compare with the current model:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_restoration.py `
  --checkpoint models\refine_net_l1.pth `
  --output reports\restoration_benchmark_current.json
```

### Adopt only if

- The candidate’s `refined` exact match is **higher than the current model**
- It is also **higher than bicubic** on the same test set

Copy only then:

```powershell
Copy-Item models\refine_net_candidate.pth models\refine_net_l1.pth -Force
```

Do not adopt it just because PSNR improves. Restoration is judged by OCR exact match.

---

## Priority 2 — Character-detector pilot (IURS)

The pilot was rejected (mAP50 0.05) and `runs/character/` plus `data/iurs/` were removed. The steps below rebuild them from the raw archive if you ever rerun it.

### Download

Dataset page: <https://data.mendeley.com/datasets/znghtgfnnf/1>

Save the ZIP here:

```text
data/iurs/IURS_Character_Detection.zip
```

Extract to:

```text
data/iurs/raw/
```

Expected structure:

```text
data/iurs/raw/
├─ train/  images + _annotations.coco.json
├─ valid/  images + _annotations.coco.json
└─ test/   images + _annotations.coco.json
```

### Prepare YOLO dataset

```powershell
.\.venv\Scripts\python.exe scripts\prepare_iurs_yolo.py `
  --raw data\iurs\raw `
  --out data\iurs\yolo `
  --limit 500
```

For the full run, remove `--limit 500`.

Output:

```text
data/iurs/yolo/
├─ images/train, images/valid, images/test
├─ labels/train, labels/valid, labels/test
└─ data.yaml
```

### Pilot training

```powershell
.\.venv\Scripts\python.exe -c "from ultralytics import YOLO; m=YOLO('yolov8n.pt'); m.train(data='data/iurs/yolo/data.yaml', epochs=5, imgsz=640, batch=8, device='cpu', project='runs/character', name='pilot', exist_ok=True)"
```

Best weights:

```text
runs/character/pilot/weights/best.pt
```

Copy to:

```text
models/character_detector_pilot.pt
```

### Evaluate

```powershell
.\.venv\Scripts\python.exe -c "from ultralytics import YOLO; m=YOLO('runs/character/pilot/weights/best.pt'); print(m.val(data='data/iurs/yolo/data.yaml', split='test', imgsz=640, device='cpu'))"
```

### Stop/go rule

- Character mAP50 is useful **and** assembled plate exact match beats the current OCR → scale to full data.
- Character detection is weak or box-to-string assembly is unreliable → stop. Keep the current OCR.

**Important:** this dataset has character boxes, not full plate strings. High character mAP does not automatically mean high plate accuracy.

---

## Priority 3 — What would actually improve plate accuracy

1. Collect **300–1,000 real plate crops with exact text** from the target camera.
2. Add **150–500 four-corner annotations** and rectify plates before OCR.
3. Support two-line plates explicitly.
4. Build a clean **150–300 image untouched test set**.
5. Add a second OCR reader and use disagreement as a review signal.
6. Calibrate the review gate on the new validation set.

Do these before spending time on more detector data.

---

## Where everything goes

| Artifact | Path |
|---|---|
| Trained models | `models/` |
| Training logs / metrics | `reports/` |
| Training runs | `runs/` |
| New datasets | `data/<name>/` |
| Documentation | `docs/` |
| Old/rejected artifacts | `attic/` |

## Budget

The **$0.93 API top-up is not needed for training**. Training uses the local CPU.

Use the credit only if you want to test the optional hosted LLM assistant. The assistant already works in **local grounded mode** with no API key.

## Verify the app after training

```powershell
cd C:\Users\suraa\Desktop\ANPR2\self-healing-anpr
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\run.ps1
```

Open <http://127.0.0.1:8000>.
