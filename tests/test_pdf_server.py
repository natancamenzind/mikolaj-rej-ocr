import http.client
import json
import threading
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import serwer_gui


@pytest.fixture
def server(monkeypatch):
    srv = ThreadingHTTPServer(('127.0.0.1', 0), serwer_gui.H)
    port = srv.server_address[1]
    monkeypatch.setattr(serwer_gui, 'PORT', port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield port
    srv.shutdown(); srv.server_close()


def request(port, method, path, body=None, host=None):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    data = json.dumps(body).encode('utf-8') if body is not None else None
    conn.request(method, path, body=data, headers={'Host': host or f'127.0.0.1:{port}',
                                                   'Content-Length': str(len(data or b''))})
    response = conn.getresponse()
    return response, response.read()


def page(image):
    data = json.loads(Path(image).with_name(Path(image).stem + '__ocr.json').read_text(encoding='utf-8'))
    return {'image': image, 'variant_id': data.get('variant_id')}


def test_page_pdf_created_and_downloadable(server, make_scan, tmp_path):
    image = make_scan(folder=tmp_path / 'do potęznego ocra')
    response, body = request(server, 'POST', '/api/pdf', {'scope': 'page', 'pages': [page(image)]})
    assert response.status == 200, body
    reply = json.loads(body)
    assert reply['path'] == str(tmp_path / 'do potęznego ocra' / '0001__ocr.pdf')
    assert Path(reply['path']).is_file()
    response, body = request(server, 'GET', reply['pdf'])
    assert response.status == 200
    assert response.getheader('Content-Type') == 'application/pdf'
    assert "filename*=UTF-8''0001__ocr.pdf" in response.getheader('Content-Disposition')
    assert body.startswith(b'%PDF')


def test_report_pdf_path(server, make_scan, tmp_path):
    pages = [page(make_scan('0001.jpg')), page(make_scan('0002.jpg'))]
    response, body = request(server, 'POST', '/api/pdf',
                             {'scope': 'report', 'report': str(tmp_path / '_RAPORT_OCR.html'), 'pages': pages})
    assert response.status == 200, body
    assert json.loads(body)['path'] == str(tmp_path / '_RAPORT_OCR.pdf')


def test_report_name_rejected(server, make_scan, tmp_path):
    response, body = request(server, 'POST', '/api/pdf',
                             {'scope': 'report', 'report': str(tmp_path / 'inny.html'), 'pages': [page(make_scan())]})
    assert response.status == 400
    assert not (tmp_path / 'inny.pdf').exists()


def test_page_scope_needs_one_page(server, make_scan):
    pages = [page(make_scan('0001.jpg')), page(make_scan('0002.jpg'))]
    response, _ = request(server, 'POST', '/api/pdf', {'scope': 'page', 'pages': pages})
    assert response.status == 400


def test_legacy_page_error(server, make_scan):
    response, body = request(server, 'POST', '/api/pdf', {'scope': 'page', 'pages': [page(make_scan(legacy=True))]})
    assert response.status == 400
    assert 'Przetwórz skan ponownie' in json.loads(body)['error']


def test_empty_pages_rejected(server):
    response, body = request(server, 'POST', '/api/pdf', {'scope': 'page', 'pages': []})
    assert response.status == 400
    assert json.loads(body)['error'] == 'Brak stron do eksportu.'


def test_pdf_get_rejects_other_files(server, make_scan, tmp_path):
    (tmp_path / 'secret.pdf').write_bytes(b'%PDF tajne')
    image = make_scan()
    for target in (tmp_path / 'secret.pdf', Path(image).with_name('0001__ocr.json'), tmp_path / 'brak__ocr.pdf'):
        response, _ = request(server, 'GET', '/pdf?path=' + urllib.parse.quote(str(target)))
        assert response.status == 404


def test_foreign_host_rejected(server, make_scan, tmp_path):
    # Bez treści: serwer odrzuca przed odczytem body, nieprzeczytane body dałoby RST zamiast odpowiedzi.
    response, _ = request(server, 'POST', '/api/pdf', host='evil.example:80')
    assert response.status == 403
    pdf = Path(make_scan()).with_name('0001__ocr.pdf'); pdf.write_bytes(b'%PDF')
    response, _ = request(server, 'GET', '/pdf?path=' + urllib.parse.quote(str(pdf)), host='evil.example:80')
    assert response.status == 403
