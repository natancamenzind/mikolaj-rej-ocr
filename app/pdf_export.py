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
import json, os, re, threading, unicodedata
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


FONT = Path(__file__).resolve().parent / 'fonts' / 'DejaVuSans.ttf'
UMASK = os.umask(0); os.umask(UMASK)                       # raz przy imporcie: umask jest globalny dla wątków
LOCK = threading.Lock()                                    # jeden eksport naraz: font i rl_config są globalne, obrazy w RAM


def _dpi(source):
    dpi = source.info.get('dpi', (0, 0))[0]
    return float(dpi) if dpi and dpi >= 50 else 300.0


def _draw_page(canvas, page):
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase.pdfmetrics import stringWidth
    import io
    rotation = int(page.get('rot', 0)) % 360
    if rotation not in (0, 90, 180, 270):
        raise ValueError('Nieobsługiwany obrót skanu.')
    name = Path(page['image']).name
    with Image.open(page['image']) as source:
        scale = 72.0 / _dpi(source)
        if rotation == 0 and source.format == 'JPEG' and source.mode in ('RGB', 'L'):
            picture, size = page['image'], source.size      # oryginalny JPEG bez ponownej kompresji
        else:
            rotated = source.convert('RGB').rotate(-rotation, expand=True) if rotation else source.convert('RGB')
            buffer = io.BytesIO(); rotated.save(buffer, 'JPEG', quality=90); buffer.seek(0)
            picture, size = ImageReader(buffer), rotated.size
    if list(size) != [page.get('width'), page.get('height')]:
        raise ValueError(f'Wymiary skanu {name} nie zgadzają się z OCR.')
    width, height = size[0] * scale, size[1] * scale
    canvas.setPageSize((width, height))
    canvas.drawImage(picture, 0, 0, width, height)
    for line in page['pdf_lines']:
        x0, y0, x1, y1 = line['bbox']
        points = line.get('baseline') or []
        base = sum(p[1] for p in points) / len(points) if points else y1 - 0.2 * (y1 - y0)
        size_pt = max(0.75 * (y1 - y0) * scale, 1.0)
        natural = stringWidth(line['text'], 'DejaVuSans', size_pt)
        if natural <= 0 or x1 <= x0:
            continue
        text = canvas.beginText()
        text.setTextRenderMode(3)                            # niewidoczny: tylko do zaznaczania i wyszukiwania
        text.setFont('DejaVuSans', size_pt)
        text.setHorizScale(100.0 * (x1 - x0) * scale / natural)
        text.setTextOrigin(x0 * scale, height - base * scale)
        text.textOut(line['text'])
        canvas.drawText(text)
    canvas.showPage()


def _cover_missing(face, pages):
    """Znaki spoza fontu (ꝛ, ꝰ, łączniki, PUA z kodeka) podpinamy pod glif „n” — tekst jest niewidoczny,
    a ToUnicode zachowa oryginalny znak. Bez tego reportlab daje kod 0 i kopiowanie zwraca U+0000."""
    glyph, width = face.charToGlyph[ord('n')], face.charWidths[ord('n')]
    for page in pages:
        for line in page['pdf_lines']:
            for code in map(ord, line['text']):
                if code not in face.charToGlyph:
                    face.charToGlyph[code] = glyph; face.charWidths[code] = width


def build_pdf(pages, out_pdf):
    """pages: [(obraz, variant_id|None)] → jeden PDF; zapis atomowy, przy błędzie stary plik zostaje."""
    with LOCK:
        return _build_pdf(pages, out_pdf)


def _build_pdf(pages, out_pdf):
    try:
        from reportlab import rl_config
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        raise ImportError('Brak biblioteki reportlab — uruchom: pip install -r requirements.txt')
    import tempfile
    loaded = [load_page(image, variant) for image, variant in pages]   # najpierw walidacja wszystkich stron
    if 'DejaVuSans' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('DejaVuSans', str(FONT)))
    _cover_missing(pdfmetrics.getFont('DejaVuSans').face, loaded)
    rl_config.useA85 = 0                                   # binarne strumienie: bez ASCII85 (+25% rozmiaru)
    out_pdf = os.path.abspath(out_pdf)
    fd, tmp = tempfile.mkstemp(prefix='.writing-', suffix='.pdf', dir=os.path.dirname(out_pdf))
    os.close(fd)
    try:
        canvas = Canvas(tmp, pageCompression=1)
        canvas.setCreator('MikolajRej OCR')
        for page in loaded:
            _draw_page(canvas, page)
        canvas.save()
        os.chmod(tmp, 0o666 & ~UMASK)                      # mkstemp daje 0600; zwykłe uprawnienia jak dla open()
        try:
            os.replace(tmp, out_pdf)
        except PermissionError:                            # Windows: plik otwarty w czytniku PDF jest zablokowany
            raise ValueError(f'Nie można zastąpić {os.path.basename(out_pdf)}. Zamknij plik PDF w przeglądarce PDF i spróbuj ponownie.')
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return out_pdf


def main(argv=None):
    import argparse, glob
    ap = argparse.ArgumentParser()
    ap.add_argument('--folder', required=True)
    ap.add_argument('--out', default='_RAPORT_OCR.pdf')
    a = ap.parse_args(argv)
    out = a.out if os.path.isabs(a.out) else os.path.join(a.folder, a.out)
    pages = [(json.load(open(p, encoding='utf-8'))['image'], None)
             for p in sorted(glob.glob(os.path.join(a.folder, '*__ocr.json')))]
    path = build_pdf(pages, out)
    print('OK:', path)
    return path


if __name__ == '__main__':
    main()
