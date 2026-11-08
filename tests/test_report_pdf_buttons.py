from pathlib import Path

import report_gen


def test_report_has_pdf_buttons(make_scan, tmp_path):
    images = [make_scan('0001.jpg'), make_scan('0002.jpg')]
    out = tmp_path / '_RAPORT_OCR.html'
    report_gen.build_report(str(tmp_path), str(out), 'M',
                            [str(Path(i).with_name(Path(i).stem + '__ocr.json')) for i in images])
    page = out.read_text(encoding='utf-8')
    assert page.count('class="pdf-all"') == 1
    assert page.count('pdf-page"') == 2
    assert "'/api/pdf'" in page
