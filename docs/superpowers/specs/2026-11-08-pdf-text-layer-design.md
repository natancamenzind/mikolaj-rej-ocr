# PDF ze skanem i niewidoczną warstwą tekstu: projekt

Data: 2026-11-08 · Status: do akceptacji

## Cel i uzasadnienie

Z gotowego wyniku OCR (`<stem>__ocr.json`) chcemy tworzyć PDF, który wygląda jak skan, ale tekst da się
w nim zaznaczać, kopiować i wyszukiwać („przeszukiwalny PDF”). Wzorcem jest `out.pdf` z ABBYY FineReader
Server dostarczony przez użytkownika: każda strona to obraz skanu (300 dpi), pod nim niewidoczny tekst,
a każda linia tekstu jest umieszczona na swojej linii na obrazie i rozciągnięta poziomo do jej szerokości.

W warstwie tekstu ląduje **tekst znormalizowany**, czyli tekst wariantu OCR pokazanego w raporcie
z naniesionymi ręcznymi poprawkami linii, znormalizowany technicznie (szczegóły niżej). Pisownia
nie jest uwspółcześniana.

## Cele

- PDF dla **całego raportu** (wszystkie strony raportu w jego kolejności, jeden plik) oraz PDF dla
  **pojedynczego skanu**, generowany z poziomu tej strony raportu.
- Tekst niewidoczny (tryb renderowania 3), skan wizualnie bez zmian.
- Polskie znaki działają przy kopiowaniu i wyszukiwaniu: „się” wpisane z klawiatury znajduje „się” z OCR.
- PDF zapisuje się obok skanów, a przeglądarka od razu go pobiera.
- Testy jednostkowe w pytest, napisane przed implementacją.

## Poza zakresem

- Uwspółcześnianie pisowni i jakakolwiek „poprawa” treści poza ręcznymi poprawkami użytkownika.
- Pozycjonowanie pojedynczych słów lub znaków (mamy tylko geometrię linii).
- PDF/A, tagowanie struktury (Tagged PDF), zakładki, metadane bibliograficzne.
- Przełączana widoczna warstwa (OCG) i widoczny podgląd tekstu.
- Generowanie PDF z CLI wsadowo dla wielu folderów (wystarczy prosty `main()` jak w `report_gen.py`).

## Czego nie wolno zepsuć

- Niewidoczny tekst nie może zasłaniać ani zmieniać wyglądu skanu.
- Nie wolno po cichu wygenerować PDF z nieaktualnym tekstem. Jeśli skan zmienił się od OCR (inny
  `scan_sha256`), eksport kończy się czytelnym błędem, tak jak dziś robi to raport i zapis poprawki.
- Serwer pozostaje lokalny (`_local_request` dla nowych endpointów). Nie dochodzą nowe nasłuchy.
- Brak `reportlab` nie może psuć reszty aplikacji. Import ma być leniwy, wewnątrz eksportu, a błąd
  ma podpowiadać `pip install -r requirements.txt`.

## Ograniczenia

- Windows, Python 3.12 jako platforma docelowa. Kod nie może zależeć od narzędzi systemowych
  (pdftotext, mutool itp.).
- `requirements.txt`: dochodzi `reportlab==5.1.0` (decyzja użytkownika; świadomie odchodzimy od zasady
  „bez nowych zależności”). Pillow już jest.
- `requirements-dev.txt` (nowy): `pytest`, `pypdf` (do odczytu tekstu z PDF w testach). Pypdf to wybór
  budującego, nie użytkownika. Obie biblioteki są w czystym Pythonie.
- Font: dołączony **DejaVu Sans** (`app/fonts/DejaVuSans.ttf`) z plikiem licencji obok
  (`app/fonts/LICENSE-DejaVu.txt`) i wpisem w `NOTICE.md`. Wbudowane fonty reportlab nie mają ą, ł, ż.
- Styl kodu: docstringi, komentarze i komunikaty UI w `app/` po polsku, styl zwięzły jak w sąsiednich plikach.
- Dane użytkownika (`_historia_ocr/`, wygenerowane PDF) nie trafiają do repo. Testy budują własne
  syntetyczne obrazy i JSON w `tmp_path`.

## Decyzje użytkownika

1. „Znormalizowany” = poprawiony OCR (wariant z raportu + ręczne poprawki linii) plus normalizacja Unicode/spacji.
2. Tekst niewidoczny.
3. Biblioteka PDF: reportlab.
4. Zakres: oba warianty, cały raport i pojedynczy skan.
5. Font: dołączony DejaVu Sans.
6. Testy: pytest.
7. Wynik: zapis obok skanów + pobranie w przeglądarce.
8. Starsze wyniki OCR bez `scan_sha256` lub `variant_id` (sprzed schematu v2): **odmowa** z czytelnym
   błędem „przetwórz skan ponownie”. Godzimy się na to, że jedna taka strona blokuje PDF całego raportu.
9. Przyciski PDF dostają **tylko nowe raporty**. Mechanizm przebudowy w `GET /report` zostaje bez zmian.

## Jak to działa

### Źródło tekstu dla jednej strony

Wejście: `(image, variant_id)`. Strona raportu ma oba pola w osadzonym `correction-source`.

1. Wczytaj `<stem>__ocr.json` obok obrazu. Jeśli brak w nim `scan_sha256` lub `variant_id` (stary
   wynik), zgłoś błąd: „Starszy wynik OCR bez weryfikacji skanu: <plik>. Przetwórz skan ponownie.”
   Jeśli `scan_sha256` nie zgadza się z obecnym plikiem obrazu, też zgłoś błąd (`ValueError`, po polsku).
2. Wybierz dokument wariantu: `ocr_history.variants_for(...)` i ten z pasującym `variant_id` i
   `scan_sha256`. Bez podanego `variant_id` weź wariant bieżącego `__ocr.json`. Dzięki temu PDF dla
   strony z raportu historii odpowiada dokładnie temu wariantowi, który widać.
3. Nanieś poprawki: `gui_line_corrections.saved_corrections(image, digest, variant_id)`. Dla każdego
   `line_id` wygrywa **najnowsza** poprawka (lista jest posortowana po `created_utc`). *Decyzja budującego.*
4. Normalizacja każdej linii: `unicodedata.normalize('NFC', …)`, zamiana dowolnych białych znaków na
   pojedynczą spację, `strip()`. Puste linie i linie bez `bbox` są pomijane. Miękkie łączniki i znaki
   przeniesienia zostają, bo tekst odpowiada linii na skanie. *Decyzja budującego.* (W danych
   użytkownika OCR zapisuje „ą” jako `a` + U+0328, więc NFC jest konieczne do wyszukiwania.)

Ta logika to czysta funkcja (np. `page_lines(document, corrections) -> [(text, bbox, baseline)]`),
testowalna bez PDF.

### Geometria i obraz

- Współrzędne w JSON są w pikselach obrazu **po obrocie** o `rot` (0/90/180/270, zgodnie z ruchem
  wskazówek zegara; tak jak w `ocr_batch.py` i `gui_line_corrections.py`). Do PDF trafia więc obraz już
  obrócony (`Image.rotate(-rot, expand=True)`), a jego rozmiar musi być równy `width × height` z JSON.
  W przeciwnym razie zgłaszamy błąd.
- Rozmiar strony w punktach: `px × 72 / dpi`, gdzie `dpi` pochodzi z metadanych obrazu (`info['dpi']`),
  a gdy go brak lub jest absurdalne (< 50), przyjmujemy 300. *Decyzja budującego.*
- Kompresja: oryginalny plik JPEG wstawiamy bez ponownej kompresji, jeśli `rot == 0` i źródło jest JPEG
  w RGB lub L. W każdym innym przypadku zapisujemy JPEG q=90 przez Pillow (PNG/TIFF 5000×7000 bez
  kompresji dałyby ogromne pliki). *Decyzja budującego.*
- Oś Y w PDF rośnie w górę: `y_pdf = (H − y_px) × skala`.

### Umieszczenie linii tekstu

Dla każdej linii (jak ABBYY):
- linia bazowa: średnia Y punktów `baseline`. Gdy jej brak, `bbox.y1 − 0.2 × wysokość bbox`;
- wysokość fontu: `0.75 × wysokość bbox` w punktach (zaznaczenie w czytniku z grubsza pokrywa linię);
- początek X: `bbox.x0`;
- skala pozioma (`Tz` / `setHorizScale`): `100 × szerokość_bbox / szerokość_tekstu_w_foncie`, więc tekst
  dokładnie wypełnia szerokość linii;
- tryb renderowania 3 (niewidoczny), font DejaVu Sans osadzony jako podzbiór (reportlab `TTFont`),
  więc kopiowanie daje poprawny Unicode.

Linie pochyłe lub zakrzywione traktujemy jak poziome (tylko bbox). Dla zaznaczania i wyszukiwania to
wystarczy. *Decyzja budującego.*

### Moduł

`app/pdf_export.py` (nowy):
- `page_lines(document, corrections)`: czysta logika tekstu (opis wyżej);
- `load_page(image, variant_id=None)`: wczytanie JSON + wariantu + poprawek, walidacja hash;
- `build_pdf(pages, out_pdf)`: `pages` to lista `(image, variant_id)`, wynik to ścieżka pliku. Zapis
  atomowy (plik tymczasowy w tym samym katalogu + `os.replace`), żeby przerwany eksport nie zostawił
  uszkodzonego PDF;
- `main()` z `--folder` (wszystkie `*__ocr.json`) i `--out`, analogicznie do `report_gen.py`.

Strona z błędem (brak JSON, zmieniony skan, brak wariantu) przerywa cały eksport z komunikatem, który
wskazuje plik. Nie powstaje częściowy PDF. *Decyzja budującego.*

### Nazwy plików wyjściowych

- Cały raport: obok pliku raportu, ta sama nazwa z rozszerzeniem `.pdf` (`_RAPORT_OCR.pdf`,
  `_POROWNANIE_OCR.pdf`).
- Pojedynczy skan: `<stem>__ocr.pdf` obok skanu.

Kolejny eksport nadpisuje poprzedni plik. *Decyzja budującego.*

### Backend (serwer)

W `do_POST`, **przed** ogólną walidacją `folder`/`items` (tak jak `/api/line-correction`):

- `POST /api/pdf` z treścią `{"pages":[{"image":…, "variant_id":…}, …], "scope":"report"|"page", "report": "<ścieżka html>"}`.
  Wymaga co najmniej jednej strony. Dla `scope=report` ścieżka wyjściowa wynika z `report`. Dla
  `scope=page` jest jedna strona i ścieżka wynika z `image`. Generowanie synchroniczne (to sekundy, nie
  minuty), więc bez systemu zadań. Odpowiedź: `{"pdf": "/pdf?path=<zakodowana ścieżka>", "path": "<ścieżka na dysku>"}`,
  a przy błędzie 400 z `{"error": …}` (ValueError, OSError, KeyError, ImportError brakującego reportlab).
- `GET /pdf?path=…`: wysyła plik z `Content-Type: application/pdf` i
  `Content-Disposition: attachment; filename*=UTF-8''…`. Serwuje tylko pliki o nazwie `*__ocr.pdf` albo
  `_RAPORT_OCR.pdf` / `_POROWNANIE_OCR.pdf`, które istnieją. Każda inna ścieżka dostaje 404. To
  zabezpieczenie przed użyciem endpointu do czytania dowolnych plików. Z tego samego powodu
  `POST /api/pdf` z `scope=report` przyjmuje tylko raporty o nazwie `_RAPORT_OCR.html` lub
  `_POROWNANIE_OCR.html`; każda inna nazwa dostaje 400.

### Frontend (raport HTML w `report_gen.py`)

- Nagłówek raportu (`.apphead`): przycisk **„Pobierz PDF z tekstem”**. Zbiera `{image, variant_id}`
  ze wszystkich `.correction-source` w kolejności stron i wysyła `scope=report`. Ścieżkę raportu zna
  serwer, który podaje ją przez `/report?path=…`; JS odczytuje ją z `location.search`.
- Nagłówek każdej strony (`.rhead`, obok przycisków zoomu): przycisk **„PDF”** z `scope=page`.
- Podczas generowania przycisk jest wyłączony, a obok pojawia się status („Tworzenie PDF…”). Po sukcesie
  przeglądarka przechodzi do `/pdf?path=…` (pobranie) i pokazuje ścieżkę zapisu. Błąd pokazujemy w statusie.
- Raport otwarty z `file://`: przyciski wyłączone z podpowiedzią „Otwórz raport w aplikacji”, tak jak
  istniejące przyciski.
- Strony z błędem w raporcie (bez `correction-source`) są pomijane przy zbieraniu. Jeśli nie zostaje
  żadna strona, pokazujemy komunikat. Strony ze starym wynikiem (bez `scan_sha256`/`variant_id`) są
  wysyłane, a serwer zwraca dla nich czytelny błąd (decyzja 8).
- Istniejące raporty nie są przebudowywane (decyzja 9). Przyciski pojawiają się w raportach
  generowanych po tej zmianie.

### Testy (pytest, `tests/`)

Uruchamianie: `pip install -r requirements-dev.txt`, potem `python -m pytest`. Testy dodają `app/`
do `sys.path` (w `tests/conftest.py`). Dane są syntetyczne: obraz z Pillow, JSON budowany w teście.

- `page_lines`: NFC (`a`+U+0328 → `ą`), zwijanie białych znaków, pomijanie pustych linii i linii bez
  bbox, najnowsza poprawka wygrywa, poprawka innej linii niczego nie zmienia.
- `load_page`: zmieniony skan → błąd, nieznany `variant_id` → błąd, brak `variant_id` w żądaniu →
  bieżący wariant, stary JSON bez `scan_sha256`/`variant_id` → błąd z prośbą o ponowny OCR.
- `build_pdf` (odczyt przez pypdf): liczba stron = liczba skanów, rozmiar strony zgodny z dpi,
  wyekstrahowany tekst zawiera znormalizowane linie z polskimi znakami (ą, ł, ż), kolejność stron
  zgodna z wejściem, obrót 90° daje stronę o zamienionych wymiarach, niezgodny rozmiar obrazu → błąd,
  zapis atomowy (przy wyjątku nie zostaje plik wyjściowy).
- Tekst jest niewidoczny: strumień treści strony zawiera `3 Tr`.
- Serwer: obsługa `/api/pdf` i `/pdf` przez wywołanie handlera z sztucznym żądaniem albo przez
  uruchomienie `ThreadingHTTPServer` na losowym porcie w teście. Do sprawdzenia: sukces, błąd 400,
  404 dla niedozwolonej nazwy pliku, 403 dla obcego `Host`.
- `report_gen`: wygenerowany HTML zawiera przyciski PDF (test na poziomie tekstu HTML).

Sprawdzenie ręczne: wygenerowany PDF otworzyć w czytniku, wyszukać słowo z polskim znakiem, zaznaczyć
linię i porównać pozycję z `out.pdf`. Uruchomienie z prawdziwym OCR wymaga modeli. Jeśli go nie
zrobimy, mówimy o tym wprost.

### Dokumentacja i porządki

- `docs/WEB_APP.md`: krótki opis eksportu PDF.
- `README.md` ↔ `README.pl.md`: jedna linia o eksporcie PDF w obu wersjach.
- `NOTICE.md`: DejaVu Sans (licencja Bitstream Vera / public domain) i reportlab (BSD) jako zależność
  instalowana.
- `AGENTS.md`: sekcja „Checking changes” dostaje `python -m pytest`; wzmianka o `tests/`.
- `SHA256SUMS`: dopisać lub zaktualizować linie zmienionych plików albo wyraźnie zgłosić, że są nieaktualne.

## Do decyzji budującego

Szczegółowe proporcje (0.75 wysokości, fallback linii bazowej), jakość JPEG, nazwy funkcji pomocniczych
i układ testów, o ile spełniają powyższe kryteria.
