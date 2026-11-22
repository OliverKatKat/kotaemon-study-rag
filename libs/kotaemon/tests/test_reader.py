import csv
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from llama_index.core.node_parser import SimpleNodeParser

from kotaemon.base import Document
from kotaemon.loaders import (
    AutoReader,
    AzureAIDocumentIntelligenceLoader,
    DocxReader,
    HtmlReader,
    MhtmlReader,
    PptxReader,
    UnstructuredReader,
)

from .conftest import skip_when_unstructured_pdf_not_installed


def test_docx_reader():
    reader = DocxReader()
    documents = reader.load_data(Path(__file__).parent / "resources" / "dummy.docx")

    assert len(documents)


def test_docx_keeps_screenshot_inside_its_section(tmp_path):
    from docx import Document as WordDocument
    from PIL import Image

    image = tmp_path / "screenshot.png"
    Image.new("RGB", (80, 40), "white").save(image)
    word = WordDocument()
    word.add_heading("Styles", level=1)
    paragraph = word.add_paragraph("Before screenshot.")
    paragraph.add_run().add_picture(str(image))
    paragraph.add_run("After screenshot.")
    word.add_heading("Other", level=1)
    word.add_paragraph("Next section.")
    path = tmp_path / "screenshot.docx"
    word.save(path)

    with patch(
        "kotaemon.loaders.docx_loader.read_image_text", return_value=("No Spacing",)
    ):
        first, second = DocxReader().load_data(path)
    assert first.metadata["section"] == "Styles"
    assert "Before screenshot.\nNo Spacing\nAfter screenshot." in first.text
    assert "No Spacing" not in second.text


def test_docx_large_table_keeps_columns_and_repeats_header(tmp_path):
    from docx import Document as WordDocument
    from llama_index.core.utils import get_tokenizer

    word = WordDocument()
    word.add_heading("Terms", level=1)
    table = word.add_table(rows=3, cols=3)
    for cell, label in zip(table.rows[0].cells, ("Name", "Definition", "Example")):
        cell.text = label
    merged = table.cell(1, 0).merge(table.cell(1, 1))
    merged.text = "Merged term"
    table.cell(1, 2).text = "First example"
    table.cell(2, 0).text = "Long term"
    words = ["opening", *(["explanation"] * 8500), "closing"]
    table.cell(2, 1).text = " ".join(words)
    table.cell(2, 2).text = "Last example"
    path = tmp_path / "large-table.docx"
    word.save(path)

    _, *tables = DocxReader().load_data(path)
    tokenizer = get_tokenizer()
    chunks = [list(csv.reader(StringIO(doc.text))) for doc in tables]
    assert len(chunks) > 2
    assert all(doc.metadata["section"] == "Terms" for doc in tables)
    assert all(len(tokenizer(doc.text)) <= 4096 for doc in tables)
    assert all(chunk[0] == ["Name", "Definition", "Example"] for chunk in chunks)
    rows = [row for chunk in chunks for row in chunk[1:]]
    assert rows[0] == ["Merged term", "", "First example"]
    assert all(row[0] == "Long term" and row[2] == "Last example" for row in rows[1:])
    assert " ".join(row[1] for row in rows).split() == words


def test_pptx_reads_native_equation_and_adjacent_text(tmp_path):
    from lxml import etree
    from pptx import Presentation

    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = "Quadratic probing"
    native_shape = etree.fromstring(
        b"""
        <mc:AlternateContent
            xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
            xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
            xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
          <mc:Choice Requires="m">
            <p:sp><p:txBody><a:p>
              <a:r><a:t>Load factor below </a:t></a:r>
              <m:oMath><m:f>
                <m:num><m:r><m:t>1</m:t></m:r></m:num>
                <m:den><m:r><m:t>2</m:t></m:r></m:den>
              </m:f></m:oMath>
            </a:p></p:txBody></p:sp>
          </mc:Choice>
        </mc:AlternateContent>
        """
    )
    slide.shapes._spTree.append(native_shape)
    path = tmp_path / "native-equation.pptx"
    deck.save(path)

    (document,) = PptxReader().load_data(path)
    assert "Load factor below (1)/(2)" in document.text
    assert document.metadata["page_label"] == 1


def test_pptx_image_ocr_keeps_wrapped_label_in_its_column():
    from types import SimpleNamespace

    from kotaemon.loaders.utils.image_ocr import read_image_text

    def box(x, y, width):
        return ((x, y), (x + width, y), (x + width, y + 18), (x, y + 18))

    result = SimpleNamespace(
        txts=["Smart", "Translate", "Accessibility", "Lookup", "Insights"],
        boxes=[box(141, 93, 44), box(212, 94, 63), box(28, 114, 85),
               box(136, 112, 53), box(137, 142, 49)],
    )
    with patch("kotaemon.loaders.utils.image_ocr._ocr") as engine:
        engine.return_value.return_value = result
        assert read_image_text(b"image", group_labels=True) == (
            "Smart Lookup", "Translate", "Accessibility", "Insights"
        )


def test_html_reader():
    reader = HtmlReader()
    documents = reader.load_data(
        Path(__file__).parent / "resources" / "html" / "dummy.html"
    )

    assert len(documents)


def test_html_reader_keeps_main_table_and_excludes_navigation(tmp_path):
    path = tmp_path / "course.html"
    path.write_text(
        '<nav>下一主题</nav><div role="main"><h1>课程</h1>'
        "<table><tr><th>算法</th><th>复杂度</th></tr>"
        "<tr><td>基数排序</td><td>O(n)</td></tr></table></div>",
        encoding="utf-8",
    )

    (doc,) = HtmlReader().load_data(path)
    assert "课程" in doc.text
    assert ["基数排序", "O(n)"] in [
        [cell.strip() for cell in line.split("|")] for line in doc.text.splitlines()
    ]
    assert "下一主题" not in doc.text


def test_pdf_preserves_slot_and_value_in_same_column(tmp_path):
    import fitz

    from kotaemon.loaders.pdf_loader import PDFThumbnailReader

    path = tmp_path / "table.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        for row in range(2):
            for column in range(3):
                x, y = 50 + 40 * column, 50 + 30 * row
                page.draw_rect(fitz.Rect(x, y, x + 40, y + 30))
        for column in (2, 0, 1):
            page.insert_text((58 + 40 * column, 70), str(column))
        page.insert_text((138, 100), "43")
        page.insert_text((58, 100), "21")
        pdf.save(path)

    text, thumbnail = PDFThumbnailReader().load_data(path)
    assert "| 0 | 1 | 2 |" in text.text
    assert "| 21 |  | 43 |" in text.text
    assert text.metadata["page_label"] == thumbnail.metadata["page_label"] == 1


def test_pdf_restores_stacked_fraction_and_raised_exponent():
    from fitz import Rect

    from kotaemon.loaders.pdf_loader import _restore_math

    def span(text, start, end, baseline, size=28, flags=0, font="CambriaMath"):
        return {
            "text": text,
            "bbox": (start, baseline - size, end, baseline + 2),
            "origin": (start, baseline),
            "size": size,
            "flags": flags,
            "font": font,
        }

    lines = [
        [span("Claim: If ", 55, 161, 149, font="Body"), span("𝜆<", 161, 204, 149)],
        [span("1", 212, 224, 132, 20)],
        [span("2", 212, 224, 163, 20), span(", and prime", 224, 300, 149, font="Body")],
        [span("𝑖", 56, 65, 363), span("2", 66, 78, 352, 20, flags=1)],
    ]
    drawings = [{"rect": Rect(212, 140, 224, 141), "items": [("re",)]}]
    assert _restore_math(lines, drawings)
    assert "".join(s["text"] for s in lines[0]) == "Claim: If λ<(1)/(2), and prime"
    assert not any(s["text"] for line in lines[1:3] for s in line)
    assert "".join(s["text"] for s in lines[3]) == "i^(2)"


def test_pdf_reader():
    reader = AutoReader("PDFReader")
    dirpath = Path(__file__).parent
    documents = reader.load_data(dirpath / "resources" / "dummy.pdf")

    # check document reader output
    assert len(documents) == 1

    first_doc = documents[0]
    assert isinstance(first_doc, Document)
    assert first_doc.text.lower().replace(" ", "") == "dummypdffile"

    # test chunking using NodeParser from llama-index
    node_parser = SimpleNodeParser.from_defaults(chunk_size=100, chunk_overlap=20)
    nodes = node_parser.get_nodes_from_documents(documents)
    assert len(nodes) > 0


@skip_when_unstructured_pdf_not_installed
def test_unstructured_pdf_reader():
    reader = UnstructuredReader()
    dirpath = Path(__file__).parent
    input_path = dirpath / "resources/dummy.pdf"
    documents = reader.load_data(input_path)

    # check document reader output
    assert len(documents) == 1

    first_doc = documents[0]
    assert isinstance(first_doc, Document)
    assert first_doc.text.lower().replace(" ", "") == "dummypdffile"

    # split documents mode
    documents = reader.load_data(input_path, split_documents=True)
    # check document reader output
    assert len(documents) == 1


def test_mhtml_reader():
    reader = MhtmlReader()
    input_path = Path(__file__).parent / "resources" / "dummy.mhtml"
    docs = reader.load_data(input_path)

    assert len(docs) == 1
    assert docs[0].text.startswith("This is a test")


@patch("azure.ai.documentintelligence.DocumentIntelligenceClient")
def test_azureai_document_intelligence_reader(mock_client):
    reader = AzureAIDocumentIntelligenceLoader(
        endpoint="https://endpoint.com",
        credential="credential",
    )
    docs = reader(Path(__file__).parent / "resources" / "dummy.pdf")

    assert len(docs) == 1
    mock_client.assert_called_once()
