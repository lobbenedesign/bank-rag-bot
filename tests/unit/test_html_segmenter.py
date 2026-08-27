from __future__ import annotations

from bs4 import BeautifulSoup

from bank_rag.ingestion.segmentation.html_segmenter import segment_html


def test_segments_page_by_heading():
    html = """
    <html><body>
    <h1>Privacy</h1>
    <p>Testo introduttivo sulla privacy.</p>
    <h2>Cookie di terze parti</h2>
    <p>Usiamo cookie di terze parti per analytics.</p>
    <h2>Dati raccolti</h2>
    <p>Raccogliamo nome, email e numero di telefono.</p>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")

    segments = segment_html(soup)

    assert [s.locator.value for s in segments] == [
        "Privacy",
        "Privacy > Cookie di terze parti",
        "Privacy > Dati raccolti",
    ]
    assert all(s.locator.kind == "section" for s in segments)
    assert "cookie di terze parti" in segments[1].text.lower()


def test_page_without_headings_falls_back_to_whole_page():
    soup = BeautifulSoup("<html><body><p>Solo un paragrafo, nessun heading.</p></body></html>", "html.parser")

    segments = segment_html(soup)

    assert len(segments) == 1
    assert segments[0].locator.kind == "whole"
