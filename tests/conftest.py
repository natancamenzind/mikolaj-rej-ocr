import json
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / 'app'
sys.path.insert(0, str(APP))

from ocr_history import sha256  # noqa: E402

DEFAULT_LINES = [
    {'i': 0, 'text': 'się ą trawa', 'bbox': [50.0, 100.0, 550.0, 160.0],
     'baseline': [[50.0, 148.0], [550.0, 150.0]]},
    {'i': 1, 'text': 'łąka  żółta', 'bbox': [50.0, 200.0, 400.0, 260.0],
     'baseline': [[50.0, 250.0], [400.0, 250.0]]},
]


@pytest.fixture
def make_scan(tmp_path):
    """Syntetyczny skan + <stem>__ocr.json w schemacie ocr_batch.py (v2)."""
    def make(name='0001.jpg', size=(600, 800), rot=0, lines=None, dpi=300, mode='RGB',
             folder=None, legacy=False, json_size=None):
        from PIL import Image
        directory = Path(folder) if folder else tmp_path
        directory.mkdir(parents=True, exist_ok=True)
        image = directory / name
        color = (230, 220, 200, 255)[:len(mode)] if mode in ('RGB', 'RGBA') else 200
        picture = Image.new(mode, size, color)
        options = {'dpi': (dpi, dpi)} if dpi else {}
        if mode == 'RGBA' and image.suffix.lower() in ('.jpg', '.jpeg'):
            raise ValueError('JPEG nie ma kanału alfa')
        picture.save(image, **options)
        width, height = (size[1], size[0]) if rot in (90, 270) else size
        if json_size:
            width, height = json_size
        rows = [dict(row, raw_text=row['text']) for row in (DEFAULT_LINES if lines is None else lines)]
        document = {'image': str(image), 'rot': rot, 'width': width, 'height': height, 'lm': False,
                    'schema_version': 2, 'lines': rows}
        if not legacy:
            document.update(scan_sha256=sha256(image), variant_id='run-' + image.stem + '-raw',
                            provenance={'engine': 'Kraken'}, label='test')
        image.with_name(image.stem + '__ocr.json').write_text(
            json.dumps(document, ensure_ascii=False), encoding='utf-8')
        return str(image)
    return make
