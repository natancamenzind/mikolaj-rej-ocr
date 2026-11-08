# AGENTS.md

Guidance for coding agents working in this repository.

## What this is

MikołajRej: a local web application and command-line pipeline for handwritten text recognition (HTR/OCR) of historical Polish documents. It is built on Kraken 7.0.2. The model weights (`.mlmodel`) and the optional Diariusz character 6-gram LM (`lm6B.bin`) are hosted on Hugging Face (`lukaszrzepinski/MikolajRej`). They are **not** stored in this repository.

The repository is a published release: code, bilingual documentation, public-domain examples, screenshots and checksums. It has no build system and no package metadata. Unit tests (pytest) live in `tests/`.

## Layout

- `app/serwer_gui.py`: local web UI. It uses only the standard library (`http.server`), binds to `127.0.0.1:${REJ_PORT:-5057}` and runs the engine scripts below as subprocesses.
- `app/gui_*.py`: helpers for the GUI (gallery, segmentation cache/pipeline, reading order, LM options, model check, line corrections).
- `app/segment_preview.py` → `app/ocr_batch.py` → `app/report_gen.py`: the pipeline (BLLA segmentation, line recognition with optional KenLM, HTML scan↔text report). The scripts talk to the GUI through `PROGRESS\t...` lines on stdout.
- `app/pdf_export.py`: searchable PDF export (scan + invisible text layer, reportlab). Font in `app/fonts/` (DejaVu Sans, licence alongside).
- `app/lm_decoder.py`, `app/ocr_history.py`, `app/ocr_comparison.py`: LM beam decoding, variant history, RAW/LM/model comparison.
- `scripts/verify_models.py`: checks model SHA256 and size using only the standard library.
- `scripts/recognize_page.py`: standalone recognizer that reads image + PAGE XML (`Coords` + `Baseline`), with no LM.
- `docs/`: model card, evaluation, provenance, quick start, web app and LM docs, `metrics.json` and `provenance.json`, `showcase/index.html`.
- `examples/`: three Polona public-domain line crops with PAGE XML and `examples.json` (sources and hashes).
- `screenshots/`: README gallery images and `readings.json`.
- `models/`: git-ignored except `models/README.md`. Model files are placed here locally.

## Environment

- Target platform: **Windows, Python 3.12**, CPU by default. Linux and macOS are not claimed for the full GUI. Windows-specific memory and process-priority checks are intentional, so do not remove them.
- Install CPU torch first, then the rest: `pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cpu`, then `pip install -r requirements.txt`.
- `requirements.txt` pins direct dependencies only. Keep the pins (notably `kraken==7.0.2`) unless the task is explicitly an upgrade. Code depends on the Kraken 7.0.2 interface.
- KenLM is optional. RAW recognition and segmentation must keep working without it.
- Environment variables: `REJ_MODEL_DIR`, `REJ_PORT`, `REJ_GPU_LOCK` (cooperative lock for optional local CUDA).

## Checking changes

Unit tests need no models: `pip install -r requirements-dev.txt`, then `python -m pytest`. Other lightweight checks:

```bash
python -m py_compile app/*.py scripts/*.py
shasum -a 256 -c SHA256SUMS        # release integrity
```

With models in `models/`: `python scripts/verify_models.py --directory models`, then `python app/serwer_gui.py` and open http://127.0.0.1:5057.

Running OCR end to end needs torch, Kraken and the model files. If you did not run it, say so. Do not report a change as verified based on syntax checks alone.

## Conventions

- **Code style:** match the existing files. Module docstrings, comments and user-facing UI strings in `app/` are in Polish. Scripts in `scripts/` are in English. The style is compact and pragmatic. Avoid adding new dependencies, especially to the GUI server, which relies on the standard library only.
- **Line endings:** LF everywhere (`.gitattributes`). PNGs are binary.
- **Bilingual docs:** `README.md` ↔ `README.pl.md` and `docs/MODEL_CARD.md` ↔ `docs/MODEL_CARD.pl.md` are pairs. Update both sides together. Several other docs (`WEB_APP.md`, `LOCAL_INFERENCE.md`, …) are Polish-only, and `QUICKSTART.md` is English.
- **Measured, hedged claims.** The documentation carefully separates what was actually run from what was not, for example: "known-DEV, not an independent test", "not independently verified", "not a benchmark". Keep that standard. Never add accuracy figures, platform-support claims or "tested" statements that are not backed by `docs/metrics.json`, `docs/EVALUATION.md` or an actual run. Keep the caveats about names, dates and digits needing human review.
- **Model names and hashes:** E26 (`MikolajRej-KRA-K11-E26-step345005.mlmodel`) is the default recognizer. E105 is experimental (`docs/MODEL_E105.md`). If you change a hash or file name, update `scripts/verify_models.py`, `docs/QUICKSTART.md`, the model cards and `app/serwer_gui.py` (`RECOMMENDED`) together.

## Hard rules

- **Do not commit model weights or native binaries.** That covers `*.mlmodel`, `*.ckpt`, `*.bin`, `*.pyd`, `*.dll` and `*.so`, all of which are already git-ignored.
- **Do not commit user/runtime data:** `app/logs/`, `app/_*.json`, `_historia_ocr/`, `_podglad_segmentacji/`, generated reports, `.env`. Local logs and report registries may contain private file paths and document history. Use only `examples/` and `docs/showcase/` for public demos.
- **Keep the server local.** It binds to `127.0.0.1` and `_local_request` rejects non-local `Host`/`Origin` and cross-site requests. Do not weaken this or add network listeners, and do not add automatic model downloads at startup.
- **Licensing is custom, not MIT.** Do not relabel the project or add licence headers. Keep upstream attributions in `NOTICE.md` and `THIRD_PARTY_APACHE_2_0.txt`: McCATMuS (CC BY 4.0), Kraken (Apache-2.0), KenLM (LGPL) and the Polona public-domain sources.
- **Checksums:** `SHA256SUMS` lists the release files (sorted by path, excluding itself). If you change files covered by it, regenerate the affected lines, or tell the user that it is now stale. At the time of writing, `README.md` and `README.pl.md` already fail the check and `docs/MODEL_E105.md` is not listed.
- Commit messages in history are short, imperative and in English or Polish.
