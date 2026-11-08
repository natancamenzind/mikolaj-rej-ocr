import json
from pathlib import Path

import pytest

import pdf_export
from gui_line_corrections import save_correction


def _json(image):
    return json.loads(Path(image).with_name(Path(image).stem + '__ocr.json').read_text(encoding='utf-8'))


def test_normalize_nfc_and_spaces():
    assert pdf_export.normalize('  się ą\t\nb ') == 'się ą b'


def test_page_lines_skips_empty_and_no_bbox():
    document = {'lines': [{'i': 0, 'text': '  ', 'bbox': [0, 0, 10, 10]},
                          {'i': 1, 'text': 'x', 'bbox': None},
                          {'i': 2, 'text': 'ok', 'bbox': [0, 0, 10, 10]}]}
    assert [row['text'] for row in pdf_export.page_lines(document, [])] == ['ok']


def test_page_lines_latest_correction_wins():
    document = {'lines': [{'i': 0, 'text': 'pierwsza', 'bbox': [0, 0, 10, 10]},
                          {'i': 1, 'text': 'druga', 'bbox': [0, 20, 10, 30]}]}
    corrections = [{'line_id': 0, 'corrected_text': 'stara'}, {'line_id': 0, 'corrected_text': 'nowa'}]
    result = pdf_export.page_lines(document, corrections)
    assert [row['text'] for row in result] == ['nowa', 'druga']
    assert result[0]['bbox'] == [0, 0, 10, 10]


def test_page_lines_whitespace_correction_dropped():
    document = {'lines': [{'i': 0, 'text': 'pierwsza', 'bbox': [0, 0, 10, 10]},
                          {'i': 1, 'text': 'druga', 'bbox': [0, 20, 10, 30]}]}
    result = pdf_export.page_lines(document, [{'line_id': 0, 'corrected_text': '   '}])
    assert [row['text'] for row in result] == ['druga']


def test_load_page_current_variant(make_scan):
    image = make_scan()
    page = pdf_export.load_page(image)
    assert page['variant_id'] == _json(image)['variant_id']
    assert [row['text'] for row in page['pdf_lines']] == ['się ą trawa', 'łąka żółta']


def test_load_page_applies_saved_correction(make_scan):
    image = make_scan()
    data = _json(image)
    save_correction({'image': image, 'scan_sha256': data['scan_sha256'], 'variant_id': data['variant_id'],
                     'line_id': 0, 'text': 'poprawiony wiersz'})
    page = pdf_export.load_page(image, data['variant_id'])
    assert page['pdf_lines'][0]['text'] == 'poprawiony wiersz'


def test_load_page_changed_scan_raises(make_scan):
    image = make_scan()
    with open(image, 'ab') as f:
        f.write(b'zmiana')
    with pytest.raises(ValueError, match='zmienił się'):
        pdf_export.load_page(image)


def test_load_page_unknown_variant_raises(make_scan):
    image = make_scan()
    with pytest.raises(ValueError, match='wariant'):
        pdf_export.load_page(image, 'nie-ma')


def test_load_page_legacy_json_raises(make_scan):
    image = make_scan(legacy=True)
    with pytest.raises(ValueError, match='Przetwórz skan ponownie'):
        pdf_export.load_page(image)


def test_load_page_missing_json_raises(make_scan):
    image = Path(make_scan())
    image.with_name(image.stem + '__ocr.json').unlink()
    with pytest.raises(ValueError, match='0001'):
        pdf_export.load_page(str(image))
