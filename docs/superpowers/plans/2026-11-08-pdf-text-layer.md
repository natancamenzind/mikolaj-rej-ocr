# PDF z niewidoczną warstwą tekstu — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eksport przeszukiwalnego PDF (skan + niewidoczny, znormalizowany tekst OCR z poprawkami) dla całego raportu i pojedynczej strony.

**Architecture:** Nowy moduł `app/pdf_export.py` (czysta logika tekstu + budowa PDF przez reportlab), dwa endpointy w `app/serwer_gui.py` (`POST /api/pdf`, `GET /pdf`), przyciski i JS w raporcie z `app/report_gen.py`.

**Tech Stack:** Python 3.12, reportlab 5.1.0, Pillow, DejaVu Sans TTF; testy: pytest + pypdf.

**Spec:** `docs/superpowers/specs/2026-11-08-pdf-text-layer-design.md`

## Global Constraints

- `requirements.txt`: dodać `reportlab==5.1.0`; nie zmieniać pozostałych pinów.
- `requirements-dev.txt` (nowy): `pytest`, `pypdf` (bez pinów sztywnych nie trzeba; wpisać `pytest>=8`, `pypdf>=6`).
- `reportlab` importowany leniwie wewnątrz `build_pdf`; brak → `ImportError` z komunikatem „Brak biblioteki reportlab — uruchom: pip install -r requirements.txt”.
- Docstringi, komentarze, komunikaty w `app/` po polsku; styl zwięzły jak w `gui_line_corrections.py`.
- Font: `app/fonts/DejaVuSans.ttf` + `app/fonts/LICENSE-DejaVu.txt` (z wydania dejavu-fonts 2.37, źródło: https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37).
- Nowe endpointy przechodzą przez `_local_request`. Dozwolone nazwy wyjściowe: `*__ocr.pdf`, `_RAPORT_OCR.pdf`, `_POROWNANIE_OCR.pdf`; dozwolone raporty: `_RAPORT_OCR.html`, `_POROWNANIE_OCR.html`.
- Nie dotykać niezacommitowanych zmian użytkownika w `app/gui_seg_pipeline.py` i `list_drives` w `app/serwer_gui.py` — nie dodawać ich do commitów (`git add -p` / tylko własne hunki).
- Testy: `python -m pytest` z katalogu repo; dane syntetyczne w `tmp_path`.

## Review Focus

- Nazwa skanu ze spacją/polskimi znakami (np. `do potęznego ocra/0003.jpg`) — URL `/pdf?path=` i `Content-Disposition` muszą działać (test w Task 3).
- Wynik ze stanem `rot=90` — obraz obracany przed wstawieniem, wymiary strony zamienione (test w Task 2).
- Tekst złożony wyłącznie z białych znaków po poprawce/normalizacji — linia pominięta, PDF dalej poprawny (test w Task 1).
- Strona bez żadnych linii z tekstem — strona PDF ze samym skanem, bez błędu (test w Task 2).
- PNG z kanałem alfa / tryb `P` — konwersja do RGB przed JPEG, bez wyjątku (test w Task 2).

---

### Task 1: Tekst strony — `page_lines` i `load_page`

**Files:**
- Create: `app/pdf_export.py`, `tests/conftest.py`, `tests/test_pdf_text.py`, `requirements-dev.txt`
- Modify: `.gitignore` (dopisać `_RAPORT_OCR.pdf`, `_POROWNANIE_OCR.pdf`, `*__ocr.pdf`, `.pytest_cache/`)

**Interfaces:**
- Produces:
  - `normalize(text: str) -> str` — NFC, `re.sub(r'\s+', ' ')`, `strip()`.
  - `page_lines(document: dict, corrections: list[dict]) -> list[dict]` — każdy element `{'text': str, 'bbox': [x0,y0,x1,y1], 'baseline': list|None}` w kolejności `document['lines']`; poprawki to rekordy z `saved_corrections` (`line_id`, `corrected_text`, posortowane rosnąco po `created_utc` — ostatnia wygrywa).
  - `load_page(image: str, variant_id: str | None = None) -> dict` — zwraca dokument wariantu z dodanym kluczem `'pdf_lines'` (wynik `page_lines`). Błędy: `ValueError` po polsku.
- `tests/conftest.py`: dodaje `app/` do `sys.path`; fixture `make_scan(tmp_path, name='0001.jpg', size=(600, 800), rot=0, lines=None, dpi=300, mode='RGB')` — zapisuje obraz Pillow, `<stem>__ocr.json` ze schematem jak w `0003__ocr.json` (`image`, `rot`, `width`, `height`, `scan_sha256`, `variant_id`, `lines[{i,text,raw_text,bbox,baseline}]`) i zwraca ścieżkę obrazu. Domyślne linie: dwie, z tekstem zawierającym `ą` (ą w NFD), `ł`, `ż`.

- [ ] **Step 1: Napisz testy** w `tests/test_pdf_text.py`:
  - `test_normalize_nfc_and_spaces`: `normalize('  się ą\t\nb ') == 'się ą b'` (wejście `'  się ą\t\nb '`).
  - `test_page_lines_skips_empty_and_no_bbox`: linie `[{'i':0,'text':'  ','bbox':[0,0,10,10]}, {'i':1,'text':'x','bbox':None}, {'i':2,'text':'ok','bbox':[0,0,10,10]}]` → `[l['text'] for l in result] == ['ok']`.
  - `test_page_lines_latest_correction_wins`: poprawki `[{'line_id':0,'corrected_text':'stara'},{'line_id':0,'corrected_text':'nowa'}]` → tekst linii 0 `== 'nowa'`, linia 1 bez zmian.
  - `test_page_lines_whitespace_correction_dropped`: poprawka `'   '` dla linii 0 → linia 0 pominięta.
  - `test_load_page_current_variant`: `load_page(img)['variant_id'] == json['variant_id']` i teksty w `pdf_lines` są w NFC (`'ą' in ...`).
  - `test_load_page_applies_saved_correction`: zapisz poprawkę przez `gui_line_corrections.save_correction({...})` dla linii 0 → `load_page(img, vid)['pdf_lines'][0]['text'] == poprawka`.
  - `test_load_page_changed_scan_raises`: nadpisz bajty obrazu po zapisaniu JSON → `pytest.raises(ValueError, match='zmienił się')`.
  - `test_load_page_unknown_variant_raises`: `load_page(img, 'nie-ma')` → `ValueError` z `'wariant'`.
  - `test_load_page_legacy_json_raises`: JSON bez `scan_sha256` i `variant_id` → `ValueError` z `'Przetwórz skan ponownie'`.
  - `test_load_page_missing_json_raises`: obraz bez `__ocr.json` → `ValueError` z nazwą pliku.

- [ ] **Step 2:** `python -m pytest tests/test_pdf_text.py -v` → FAIL (`ModuleNotFoundError: pdf_export`).

- [ ] **Step 3: Implementuj** w `app/pdf_export.py` (docstring modułu po polsku, opis jak w spec). `load_page`: czyta sidecar `Path(image).with_name(stem+'__ocr.json')`; brak `scan_sha256`/`variant_id` → „Starszy wynik OCR bez weryfikacji skanu: <nazwa>. Przetwórz skan ponownie.”; `sha256(image) != scan_sha256` → „Skan <nazwa> zmienił się od OCR. Przetwórz skan ponownie.”; wariant przez `variants_for(dict(current, image=str(image)))` z dopasowaniem `variant_id` i `scan_sha256` (brak → „Nie znaleziono wariantu OCR … Odśwież raport.”); poprawki przez `saved_corrections(image, digest, variant_id)`.

- [ ] **Step 4:** `python -m pytest tests/test_pdf_text.py -v` → PASS.

- [ ] **Step 5: Commit** `git add app/pdf_export.py tests/ requirements-dev.txt .gitignore && git commit -m "Add page text normalization for PDF export"`

### Task 2: Budowa PDF — `build_pdf`

**Files:**
- Modify: `app/pdf_export.py`, `requirements.txt`, `NOTICE.md`
- Create: `app/fonts/DejaVuSans.ttf`, `app/fonts/LICENSE-DejaVu.txt`, `tests/test_pdf_build.py`

**Interfaces:**
- Consumes: `load_page`, fixture `make_scan` (Task 1).
- Produces: `build_pdf(pages: list[tuple[str, str | None]], out_pdf: str) -> str` — zwraca `out_pdf`; `main()` z `--folder`, `--out` (domyślnie `_RAPORT_OCR.pdf` w folderze), strony = posortowane `*__ocr.json` → `(image z JSON, None)`.

Wartości ze spec: dpi z `Image.info['dpi'][0]`, gdy brak lub `< 50` → 300; skala `72/dpi`; obraz obrócony `rotate(-rot, expand=True)`, rozmiar musi równać się `(width, height)` z JSON, inaczej `ValueError('Wymiary skanu … nie zgadzają się z OCR.')`; JPEG źródłowy wstawiany bez rekompresji gdy `rot == 0` i format JPEG w trybie RGB/L, inaczej `convert('RGB')` + JPEG q=90 do `BytesIO` (`ImageReader`); linia bazowa = średnia Y punktów `baseline`, brak → `y1 - 0.2*(y1-y0)`; rozmiar fontu `0.75*(y1-y0)*skala`; `setHorizScale(100*szer_bbox_pt/stringWidth)`; `setTextRenderMode(3)`; font `TTFont('DejaVuSans', app/fonts/DejaVuSans.ttf)`. Zapis atomowy: `tempfile.mkstemp(dir=katalog_wyjścia, suffix='.pdf')` → `os.replace`; przy wyjątku plik tymczasowy usuwany. Wszystkie strony ładowane (`load_page`) przed rozpoczęciem rysowania, błąd strony → `ValueError` z nazwą pliku.

- [ ] **Step 1: Pobierz font**: `curl -L` archiwum `dejavu-fonts-ttf-2.37.tar.bz2` z wydania 2.37 do scratchpad, wypakuj `ttf/DejaVuSans.ttf` i `LICENSE` → `app/fonts/`. Sprawdź: `python -c "from PIL import ImageFont; ImageFont.truetype('app/fonts/DejaVuSans.ttf', 12).getbbox('ąłż')"` nie rzuca.

- [ ] **Step 2: Napisz testy** w `tests/test_pdf_build.py` (odczyt `pypdf.PdfReader`):
  - `test_pages_in_order_with_polish_text`: dwa skany o różnych tekstach → `len(reader.pages) == 2`, `'się' in pages[0].extract_text()` i tekst 2. skanu na stronie 2.
  - `test_page_size_from_dpi`: skan 600×800 px, dpi 300 → `mediabox` ≈ `(144, 192)` pt (±0.5); dpi 150 → `(288, 384)`; brak dpi → jak 300.
  - `test_text_is_invisible`: `b'3 Tr' in pages[0].get_contents().get_data()`.
  - `test_rotated_scan`: `rot=90`, obraz 800×600, JSON `width=600,height=800` → mediabox `(144, 192)`.
  - `test_size_mismatch_raises`: JSON z `width` o 10 px innym → `ValueError`, plik wyjściowy nie istnieje.
  - `test_failure_keeps_previous_file`: istniejący `out.pdf` z treścią `b'stary'`, druga strona z błędem → wyjątek, `out.pdf` nadal `b'stary'`, w katalogu brak plików `*.pdf` poza nim.
  - `test_page_without_text`: skan z `lines=[]` → 1 strona, bez wyjątku.
  - `test_png_rgba_input`: `make_scan(name='a.png', mode='RGBA')` → PDF powstaje.
  - `test_jpeg_passthrough`: dla JPEG `rot=0` bajty obrazu w PDF (`pages[0].images[0].data`) równe bajtom pliku źródłowego.

- [ ] **Step 3:** `python -m pytest tests/test_pdf_build.py -v` → FAIL (`build_pdf` brak).

- [ ] **Step 4: Implementuj** `build_pdf` i `main` w `app/pdf_export.py`; dodaj `reportlab==5.1.0` do `requirements.txt`; w `NOTICE.md` akapit o DejaVu Sans (licencja Bitstream Vera + zmiany DejaVu w domenie publicznej, plik `app/fonts/LICENSE-DejaVu.txt`) i o reportlab (BSD, instalowany z PyPI, nie dołączany).

- [ ] **Step 5:** `python -m pytest -v` → wszystkie PASS.

- [ ] **Step 6: Commit** `git commit -m "Build searchable PDF with invisible text layer"` (tylko pliki tego taska).

### Task 3: Endpointy serwera

**Files:**
- Modify: `app/serwer_gui.py` (`do_GET` — nowa gałąź `/pdf`; `do_POST` — gałąź `/api/pdf` zaraz po `/api/line-correction`)
- Create: `tests/test_pdf_server.py`

**Interfaces:**
- Consumes: `pdf_export.build_pdf` (Task 2).
- Produces (dla Task 4):
  - `POST /api/pdf` body `{"scope":"report","report":"<ścieżka .html>","pages":[{"image":str,"variant_id":str|null}]}` lub `{"scope":"page","pages":[jedna strona]}` → 200 `{"pdf":"/pdf?path=<quote(ścieżka)>","path":"<ścieżka>"}`; 400 `{"error":str}`.
  - `GET /pdf?path=…` → 200 `application/pdf` + `Content-Disposition: attachment; filename*=UTF-8''<quote(basename)>`; 404 dla nazw spoza dozwolonych lub nieistniejących.
- Ścieżki wyjściowe: `scope=report` → `os.path.splitext(report)[0] + '.pdf'` (raport musi mieć basename `_RAPORT_OCR.html` lub `_POROWNANIE_OCR.html`, inaczej 400 „Nieobsługiwany raport.”); `scope=page` → `os.path.splitext(image)[0] + '__ocr.pdf'`, dokładnie jedna strona. Brak stron → 400 „Brak stron do eksportu.”. Wyjątki `ValueError, OSError, KeyError, TypeError, ImportError` → 400. `do_POST` czyta body przed rozgałęzieniem — zachować.

- [ ] **Step 1: Napisz testy** w `tests/test_pdf_server.py`. Fixture `server`: `srv = ThreadingHTTPServer(('127.0.0.1', 0), serwer_gui.H)`, `monkeypatch.setattr(serwer_gui, 'PORT', srv.server_address[1])`, wątek `serve_forever`, na końcu `shutdown()`. Żądania przez `http.client` z `Host: 127.0.0.1:<port>`.
  - `test_page_pdf_created_and_downloadable`: skan w katalogu `tmp_path/'do potęznego ocra'` → POST `scope=page` 200; plik `0001__ocr.pdf` istnieje; GET na zwrócony `pdf` → 200, `Content-Type: application/pdf`, body zaczyna się od `b'%PDF'`, nagłówek zawiera `filename*=UTF-8''0001__ocr.pdf`.
  - `test_report_pdf_path`: `scope=report`, `report=<dir>/_RAPORT_OCR.html` (plik nie musi istnieć), dwie strony → `path` kończy się `_RAPORT_OCR.pdf`.
  - `test_report_name_rejected`: `report=<dir>/inny.html` → 400.
  - `test_legacy_page_error`: JSON bez `scan_sha256` → 400, `'Przetwórz skan ponownie' in error`.
  - `test_empty_pages_rejected`: `pages=[]` → 400.
  - `test_pdf_get_rejects_other_files`: GET `/pdf?path=<tmp>/secret.pdf` (istnieje) → 404; `/pdf?path=<plik .json>` → 404.
  - `test_foreign_host_rejected`: POST z `Host: evil.example:80` → 403.

- [ ] **Step 2:** `python -m pytest tests/test_pdf_server.py -v` → FAIL (404/brak gałęzi).

- [ ] **Step 3: Implementuj** obie gałęzie w `app/serwer_gui.py` (import `pdf_export` leniwie w gałęzi; plik wysyłany z `Content-Length`). Helper dozwolonych nazw: `PDF_NAMES = ('_RAPORT_OCR.pdf', '_POROWNANIE_OCR.pdf')` + `endswith('__ocr.pdf')`.

- [ ] **Step 4:** `python -m pytest -v` → PASS.

- [ ] **Step 5: Commit** tylko własne hunki: `git add -p app/serwer_gui.py` + test → `git commit -m "Serve PDF export endpoints"`.

### Task 4: Przyciski w raporcie

**Files:**
- Modify: `app/report_gen.py` (`_page_block` — przycisk w `.rhead`; `build_report` — przycisk i status w `.apphead`; `CSS`, `JS`)
- Create: `tests/test_report_pdf_buttons.py`

**Interfaces:**
- Consumes: `POST /api/pdf`, `GET /pdf` (Task 3).
- Markup: `.apphead` → `<button class="pdf-all">Pobierz PDF z tekstem</button><span class="pdf-status" role="status"></span>`; `.rhead` (przed przyciskami zoomu) → `<button class="zbtn pdf-page" title="PDF tej strony">PDF</button>`; status strony we wspólnym `.pdf-status` nagłówka.
- JS: strony = `JSON.parse(.correction-source)` → `{image, variant_id}`; raport = `new URLSearchParams(location.search).get('path')`; przy `file:` wszystkie `.pdf-all`/`.pdf-page` `disabled` + status „Otwórz raport w aplikacji, aby utworzyć PDF.”; w trakcie: `disabled`, „Tworzenie PDF…”; sukces: status „Zapisano: <path>”, `location.href = reply.pdf`; błąd: status = `reply.error`; brak stron → „Brak stron do eksportu.”.

- [ ] **Step 1: Napisz test** `test_report_has_pdf_buttons`: `build_report(tmp, out, 'M', [json z make_scan])` → HTML zawiera `class="pdf-all"`, dokładnie jedno `pdf-page` na stronę, i `'/api/pdf'` w skrypcie.
- [ ] **Step 2:** `python -m pytest tests/test_report_pdf_buttons.py -v` → FAIL.
- [ ] **Step 3: Implementuj** markup, CSS (styl jak `.zbtn`; `.pdf-all` jak przycisk akcentu `--pri`) i JS.
- [ ] **Step 4:** `python -m pytest -v` → PASS.
- [ ] **Step 5: Weryfikacja w aplikacji**: uruchom `REJ_PORT=5057 python app/serwer_gui.py`, otwórz `http://127.0.0.1:5057/report?path=<folder z prawdziwym __ocr.json>/_RAPORT_OCR.html` (wygeneruj raport przez `python app/report_gen.py --folder …` dla `~/Downloads/do potęznego ocra`), kliknij oba przyciski, sprawdź pobranie i `pdftotext` wynikowego PDF (polskie znaki, `ą` jako jeden znak). Wygenerowanych plików nie commitować.
- [ ] **Step 6: Commit** `git commit -m "Add PDF export buttons to OCR report"`.

### Task 5: Dokumentacja i sumy kontrolne

**Files:**
- Modify: `docs/WEB_APP.md`, `README.md`, `README.pl.md`, `AGENTS.md`, `SHA256SUMS`

- [ ] **Step 1:** `docs/WEB_APP.md` — sekcja „Eksport PDF z warstwą tekstu” (co trafia do tekstu: wariant z raportu + poprawki, NFC; gdzie zapisuje; odmowa dla starszych wyników; tylko nowe raporty mają przyciski; nazwy i daty wymagają przeglądu człowieka). `README.md` ↔ `README.pl.md` — po jednym zdaniu w obu. `AGENTS.md` — w „Layout” `tests/`, `app/pdf_export.py`, `app/fonts/`; w „Checking changes” `pip install -r requirements-dev.txt` i `python -m pytest`; usunąć zdanie „no test suite”.
- [ ] **Step 2:** Zaktualizuj w `SHA256SUMS` linie zmienionych plików, które już są na liście (`shasum -a 256 <plik>`), zachowując sortowanie; nie dopisywać nowych plików bez sprawdzenia, czy podobne pliki są na liście (zgłosić użytkownikowi). Uruchom `shasum -a 256 -c SHA256SUMS` i zanotuj, które pozycje dalej nie przechodzą (README.* i MODEL_E105 były nieaktualne już wcześniej).
- [ ] **Step 3:** `python -m py_compile app/*.py scripts/*.py && python -m pytest -v` → PASS.
- [ ] **Step 4: Commit** `git commit -m "Document PDF export"`.
