#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_export.py — przeszukiwalny PDF: skan + niewidoczna warstwa tekstu (jak „tekst pod obrazem” z ABBYY).

Tekst każdej strony to wariant OCR pokazany w raporcie (<stem>__ocr.json lub zapis z _historia_ocr)
z naniesionymi ręcznymi poprawkami linii (najnowsza wygrywa), znormalizowany: Unicode NFC
(OCR zapisuje „ą” jako a + ogonek), pojedyncze spacje. Pisownia nie jest uwspółcześniana.
Każda linia leży na swoim bbox i jest rozciągnięta poziomo do jego szerokości.

Użycie (z GUI):
  from pdf_export import build_pdf
  build_pdf([(obraz, variant_id), ...], out_pdf)

Samodzielnie:
  python pdf_export.py --folder FOLDER --out _RAPORT_OCR.pdf
"""
import json, re, unicodedata
from pathlib import Path
from ocr_history import sha256, variants_for
from gui_line_corrections import saved_corrections


def normalize(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text or '')).strip()


def page_lines(document, corrections):
    """Linie do warstwy tekstu: [{'text','bbox','baseline'}] w kolejności OCR, bez pustych i bez geometrii."""
    fixed = {row['line_id']: row['corrected_text'] for row in corrections}   # posortowane: ostatnia wygrywa
    out = []
    for line in document.get('lines', []):
        text = normalize(fixed.get(line.get('i'), line.get('text', '')))
        if text and line.get('bbox'):
            out.append({'text': text, 'bbox': line['bbox'], 'baseline': line.get('baseline')})
    return out


def load_page(image, variant_id=None):
    """Dokument wariantu OCR dla skanu, z gotowymi liniami w 'pdf_lines'. Błędy: ValueError."""
    image = Path(image)
    sidecar = image.with_name(image.stem + '__ocr.json')
    if not sidecar.is_file():
        raise ValueError(f'Brak wyniku OCR dla {image.name}. Przetwórz skan.')
    current = json.loads(sidecar.read_text(encoding='utf-8'))
    digest = current.get('scan_sha256')
    if not digest or not current.get('variant_id'):
        raise ValueError(f'Starszy wynik OCR bez weryfikacji skanu: {image.name}. Przetwórz skan ponownie.')
    if sha256(image) != digest:
        raise ValueError(f'Skan {image.name} zmienił się od OCR. Przetwórz skan ponownie.')
    wanted = variant_id or current['variant_id']
    document = next((d for d in variants_for(dict(current, image=str(image)))
                     if d.get('variant_id') == wanted and d.get('scan_sha256') == digest), None)
    if document is None:
        raise ValueError(f'Nie znaleziono wariantu OCR dla {image.name}. Odśwież raport.')
    return dict(document, image=str(image), pdf_lines=page_lines(document, saved_corrections(image, digest, wanted)))
