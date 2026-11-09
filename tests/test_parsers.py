"""Тесты разбора документов, нормализации и нарезки на фрагменты."""

import itertools
from pathlib import Path

import pytest

from app.parsers.chunker import chunk_units
from app.parsers.docx import parse_docx
from app.parsers.normalizer import normalize_text, strip_running_lines
from app.parsers.pdf import parse_pdf
from app.parsers.types import NoTextLayerError, Unit
from app.parsers.xlsx import parse_xlsx

DATA = Path(__file__).resolve().parents[1] / "data"


def test_blender_passport_pdf_pages_and_text():
    units = parse_pdf(DATA / "blender_passport.pdf")

    joined = "\n".join(unit.text for unit in units)
    assert "800 Вт" in joined
    assert "24 месяца" in joined
    assert all(unit.page in (1, 2) for unit in units)
    assert {unit.page for unit in units} == {1, 2}


def test_boiler_scan_pdf_raises_no_text_layer():
    with pytest.raises(NoTextLayerError, match="похоже на скан"):
        parse_pdf(DATA / "boiler_scan.pdf")


def test_kettle_manual_pdf_parses():
    units = parse_pdf(DATA / "kettle_manual.pdf")

    assert units
    assert all(unit.page == 1 for unit in units)


def test_kettle_spec_xlsx_rows_with_headers():
    units = parse_xlsx(DATA / "kettle_spec.xlsx")

    row = next(unit for unit in units if unit.sku == "KTL-1700")
    assert row.kind == "row"
    assert row.section == "Спецификация"
    assert row.header is not None
    assert "Мощность, Вт" in row.header
    assert row.text.startswith("KTL-1700: ")
    assert "Мощность, Вт 2200" in row.text


def test_blender_kp_docx_table_rows():
    units = parse_docx(DATA / "blender_kp.docx")

    row = next(unit for unit in units if "BLD-800" in unit.text)
    assert row.kind == "row"
    assert row.sku == "BLD-800"
    assert "2 190" in row.text
    assert row.section == "Прайс-лист (опт)"


def test_normalize_text_hyphen_ligatures_and_spaces():
    assert normalize_text("мощ-\nность") == "мощность"
    assert normalize_text("пол-литра") == "пол-литра"
    assert normalize_text("ﬁle ﬂow") == "file flow"
    assert normalize_text("2 190") == "2 190"
    assert normalize_text("a\t\tb   c  \n  d ") == "a b c\nd"
    assert normalize_text("a\n\n\n\n\nb") == "a\n\nb"


def test_strip_running_lines_two_pages_keeps_unique_text():
    pages = ["Шапка стр. 1\nТолько здесь", "Шапка стр. 2\nА тут нет"]

    assert strip_running_lines(pages) == ["Только здесь", "А тут нет"]


def test_strip_running_lines_needs_two_pages_on_half_of_document():
    pages = ["Шапка\nтекст 1", "Шапка\nтекст 2", "текст 3", "текст 4"]

    assert strip_running_lines(pages) == ["текст 1", "текст 2", "текст 3", "текст 4"]


def test_strip_running_lines_single_page_untouched():
    assert strip_running_lines(["Шапка\nтекст"]) == ["Шапка\nтекст"]


def test_chunk_table_rows_are_not_split():
    header = "мощность, Вт; объём чаши, л"
    units = [
        Unit(
            text=f"BLD-{i}: мощность {i} Вт; объём чаши {i} л",
            section="Таблица",
            kind="row",
            header=header,
            sku=f"BLD-{i}",
        )
        for i in range(200)
    ]
    units.insert(
        100,
        Unit(
            text="X-LONG: " + "очень длинная строка " * 40,
            section="Таблица",
            kind="row",
            header=header,
            sku="X-LONG",
        ),
    )

    chunks = chunk_units(units, size=300)

    row_lines = []
    for chunk in chunks:
        assert chunk.kind == "row"
        lines = chunk.text.split("\n")
        assert lines[0] == f"Колонки: {header}"
        row_lines.extend(lines[1:])
    assert sorted(row_lines) == sorted(unit.text for unit in units)
    assert [chunk.position for chunk in chunks] == list(range(len(chunks)))


def test_chunk_text_overlaps_and_keeps_order():
    words = [f"слово{i}" for i in range(500)]
    unit = Unit(text=" ".join(words), page=3, section="Раздел")

    chunks = chunk_units([unit], size=200, overlap=50)

    assert len(chunks) > 1
    assert [chunk.position for chunk in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert len(chunk.text) <= 200
        assert chunk.text == chunk.text.strip()
        assert chunk.page == 3
        assert chunk.section == "Раздел"
        assert chunk.kind == "text"
    for previous, following in itertools.pairwise(chunks):
        assert following.text[:15] in previous.text
    covered = " ".join(chunk.text for chunk in chunks)
    assert all(word in covered.split() for word in words)


def test_chunk_keeps_pages_of_separate_units():
    units = [Unit(text="первая страница", page=1), Unit(text="вторая страница", page=2), Unit(text="   ")]

    chunks = chunk_units(units)

    assert [(chunk.text, chunk.page, chunk.position) for chunk in chunks] == [
        ("первая страница", 1, 0),
        ("вторая страница", 2, 1),
    ]
