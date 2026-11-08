import json
import os
from pathlib import Path

import pytest
from pypdf import PdfReader

import pdf_export


def _size(page):
    return float(page.mediabox.width), float(page.mediabox.height)


def test_pages_in_order_with_polish_text(make_scan, tmp_path):
    first = make_scan('0001.jpg')
    second = make_scan('0002.jpg', lines=[{'i': 0, 'text': 'druga strona', 'bbox': [50, 100, 500, 160],
                                           'baseline': [[50, 150], [500, 150]]}])
    out = pdf_export.build_pdf([(first, None), (second, None)], str(tmp_path / 'out.pdf'))
    pages = PdfReader(out).pages
    assert len(pages) == 2
    text = pages[0].extract_text()
    assert 'się ą trawa' in text and 'łąka żółta' in text
    assert 'druga strona' in pages[1].extract_text()


@pytest.mark.parametrize('dpi,expected', [(300, (144, 192)), (150, (288, 384)), (None, (144, 192))])
def test_page_size_from_dpi(make_scan, tmp_path, dpi, expected):
    image = make_scan('0001.png', dpi=dpi)
    out = pdf_export.build_pdf([(image, None)], str(tmp_path / 'out.pdf'))
    assert _size(PdfReader(out).pages[0]) == pytest.approx(expected, abs=0.5)


def test_text_is_invisible(make_scan, tmp_path):
    out = pdf_export.build_pdf([(make_scan(), None)], str(tmp_path / 'out.pdf'))
    assert b'3 Tr' in PdfReader(out).pages[0].get_contents().get_data()


def test_rotated_scan(make_scan, tmp_path):
    image = make_scan('0001.jpg', size=(800, 600), rot=90)
    out = pdf_export.build_pdf([(image, None)], str(tmp_path / 'out.pdf'))
    assert _size(PdfReader(out).pages[0]) == pytest.approx((144, 192), abs=0.5)


def test_size_mismatch_raises(make_scan, tmp_path):
    image = make_scan(json_size=(610, 800))
    out = tmp_path / 'out.pdf'
    with pytest.raises(ValueError, match='Wymiary'):
        pdf_export.build_pdf([(image, None)], str(out))
    assert not out.exists()


def test_failure_keeps_previous_file(make_scan, tmp_path):
    good = make_scan('0001.jpg')
    bad = make_scan('0002.jpg', legacy=True)
    out = tmp_path / 'out.pdf'
    out.write_bytes(b'stary')
    with pytest.raises(ValueError, match='0002'):
        pdf_export.build_pdf([(good, None), (bad, None)], str(out))
    assert out.read_bytes() == b'stary'
    assert sorted(p.name for p in tmp_path.glob('*.pdf')) == ['out.pdf']


def test_render_error_leaves_no_temp_file(make_scan, tmp_path, monkeypatch):
    image = make_scan()
    monkeypatch.setattr(pdf_export, '_draw_page', lambda *a: (_ for _ in ()).throw(OSError('dysk')))
    with pytest.raises(OSError):
        pdf_export.build_pdf([(image, None)], str(tmp_path / 'out.pdf'))
    assert list(tmp_path.glob('*.pdf')) == []


def test_page_without_text(make_scan, tmp_path):
    out = pdf_export.build_pdf([(make_scan(lines=[]), None)], str(tmp_path / 'out.pdf'))
    assert len(PdfReader(out).pages) == 1


def test_png_rgba_input(make_scan, tmp_path):
    out = pdf_export.build_pdf([(make_scan('a.png', mode='RGBA'), None)], str(tmp_path / 'out.pdf'))
    assert len(PdfReader(out).pages) == 1


def test_jpeg_passthrough(make_scan, tmp_path):
    image = make_scan('0001.jpg')
    out = pdf_export.build_pdf([(image, None)], str(tmp_path / 'out.pdf'))
    xobjects = PdfReader(out).pages[0]['/Resources']['/XObject']
    stream = next(x.get_object() for x in xobjects.values() if x.get_object()['/Subtype'] == '/Image')
    assert list(stream['/Filter']) == ['/DCTDecode']
    assert stream._data == Path(image).read_bytes()          # surowy strumień = oryginalny plik JPEG


def test_main_exports_folder(make_scan, tmp_path):
    make_scan('0002.jpg'); make_scan('0001.jpg')
    assert pdf_export.main(['--folder', str(tmp_path)]) == str(tmp_path / '_RAPORT_OCR.pdf')
    assert len(PdfReader(str(tmp_path / '_RAPORT_OCR.pdf')).pages) == 2


@pytest.mark.skipif(os.name == 'nt', reason='uprawnienia POSIX')
def test_output_has_normal_permissions(make_scan, tmp_path):
    out = pdf_export.build_pdf([(make_scan(), None)], str(tmp_path / 'out.pdf'))
    umask = os.umask(0); os.umask(umask)
    assert os.stat(out).st_mode & 0o777 == 0o666 & ~umask
