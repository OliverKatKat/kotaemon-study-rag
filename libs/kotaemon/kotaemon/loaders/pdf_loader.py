import base64
import re
import unicodedata
from collections import Counter, defaultdict
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

from decouple import config
from fsspec import AbstractFileSystem
from llama_index.readers.file import PDFReader
from PIL import Image

from kotaemon.base import Document

from .utils.image_ocr import read_image_text

PDF_LOADER_DPI = config("PDF_LOADER_DPI", default=40, cast=int)
_table_lock = Lock()


def _restore_math(lines, drawings) -> bool:
    """Keep raised scripts and stacked fractions in the text of an equation."""
    math_spans = [
        (line, span)
        for line in lines
        for span in line
        if "math" in span["font"].lower() and span["text"].strip()
    ]
    if not math_spans:
        return False

    changed = False
    for path in drawings:
        bar = path["rect"]
        if len(path["items"]) != 1 or not (
            2 <= bar.width <= 96 and bar.height <= 2
        ):
            continue
        above = []
        below = []
        for line, span in math_spans:
            x, y = span["origin"]
            if not span["text"] or x < bar.x0 - 2 or span["bbox"][2] > bar.x1 + 2:
                continue
            if 0 < bar.y0 - y <= span["size"] * 0.65:
                above.append((line, span))
            elif 0 < y - bar.y1 <= span["size"] * 1.25:
                below.append((line, span))
        if len(above) != 1 or len(below) != 1:
            continue
        _, numerator = above[0]
        denominator_line, denominator = below[0]
        anchors = [
            (line, span)
            for line, span in math_spans
            if span["text"]
            and 0 <= bar.x0 - span["bbox"][2] <= span["size"] * 0.6
            and abs(span["origin"][1] - bar.y0) <= span["size"] * 0.4
        ]
        if len(anchors) != 1:
            continue
        anchor_line, anchor = anchors[0]
        anchor["text"] += f"({numerator['text']})/({denominator['text']})"
        numerator["text"] = denominator["text"] = ""
        if denominator_line is not anchor_line:
            for span in denominator_line:
                if span["origin"][0] >= bar.x1 - 2 and abs(
                    span["origin"][1] - anchor["origin"][1]
                ) <= 2:
                    anchor_line.append({**span})
                    span["text"] = ""
        changed = True

    for line in lines:
        for previous, span in zip(line, line[1:]):
            if (
                span["text"].strip()
                and "math" in span["font"].lower()
                and span["font"] == previous["font"]
                and span["flags"] & 1  # PyMuPDF superscript flag
                and span["size"] < previous["size"] * 0.85
            ):
                span["text"] = f"^({span['text'].strip()})"
                changed = True
        for span in line:
            if "math" in span["font"].lower():
                span["text"] = unicodedata.normalize("NFKC", span["text"])
    return changed


def _restore_outlined_parentheses(page, lines, drawings) -> bool:
    """Recover outlined delimiters only if OCR agrees with the native expression."""
    import fitz

    outlines = [
        path["rect"]
        for path in drawings
        if path["type"] == "f"
        and 8 <= path["rect"].height <= 60
        and sum(item[0] == "c" for item in path["items"]) >= 4
    ]
    if not outlines:
        return False

    without_delimiters = str.maketrans("", "", "()")
    superscript_digits = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
    rows = defaultdict(list)
    for line in lines:
        baseline = None
        for span in line:
            if "math" in span["font"].lower() and span["text"].strip():
                if baseline is None or not span["text"].startswith("^("):
                    baseline = round(span["origin"][1])
                rows[baseline].append(span)

    changed = False
    for baseline, spans in rows.items():
        spans.sort(key=lambda span: span["origin"][0])
        native = "".join(span["text"] for span in spans)
        if "(" in re.sub(r"\^\([^)]+\)", "", native):
            continue
        clip = fitz.Rect(spans[0]["bbox"])
        for span in spans[1:]:
            clip |= fitz.Rect(span["bbox"])
        nearby = [
            box
            for box in outlines
            if box.y0 <= baseline <= box.y1 and box.intersects(clip)
        ]
        if not nearby:
            continue
        for box in nearby:
            clip |= box
        clip += (-2, -2, 2, 2)
        raster = page.get_pixmap(dpi=200, clip=clip).tobytes("png")
        recognized = " ".join(read_image_text(raster, single_line=True))
        if not (recognized.count("(") == recognized.count(")") > 0):
            continue
        recognized = re.sub(
            r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+",
            lambda run: f"^({run[0].translate(superscript_digits)})",
            recognized,
        )
        from_ocr = unicodedata.normalize("NFKC", recognized).translate(without_delimiters)
        if "".join(from_ocr.split()) != "".join(
            native.translate(without_delimiters).split()
        ):
            continue
        spans[0]["text"] = recognized
        for span in spans[1:]:
            span["text"] = ""
        changed = True
    return changed


def _native_text_with_layout(page, fallback: str) -> str:
    """Use page geometry when it recovers structure missing from plain text."""
    import fitz

    if page.rotation:
        return fallback
    text_lines = [
        line
        for block in page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]
        for line in block.get("lines", [])
    ]
    if not text_lines or any(line["dir"] != (1.0, 0.0) for line in text_lines):
        return fallback

    drawings = page.get_drawings()
    lines = [line["spans"] for line in text_lines]
    restored_math = _restore_math(lines, drawings)
    restored_parentheses = _restore_outlined_parentheses(page, lines, drawings)
    tables_at = defaultdict(list)
    table_spans = set()
    if len(drawings) >= 6:
        with _table_lock:
            tables = [
                (fitz.Rect(table.bbox), table.extract())
                for table in page.find_tables(strategy="lines_strict").tables
                if table.row_count > 1 and table.col_count > 1
            ]
        for box, rows in tables:
            spans = [
                span
                for line in lines
                for span in line
                if box.contains(fitz.Rect(span["bbox"]))
            ]
            native_chars = Counter(
                c for span in spans for c in span["text"] if not c.isspace()
            )
            table_chars = Counter(
                c for row in rows for cell in row for c in cell or "" if not c.isspace()
            )
            if not table_chars or native_chars != table_chars:
                continue
            table_spans.update(map(id, spans))
            position = next(
                (i for i, line in enumerate(text_lines) if line["bbox"][1] >= box.y1),
                len(lines),
            )
            cells = [
                [(cell or "").replace("\n", " ").replace("|", r"\|") for cell in row]
                for row in rows
            ]
            cells.insert(1, ["---"] * len(cells[0]))
            tables_at[position].append(
                "\n".join("| " + " | ".join(row) + " |" for row in cells)
            )

    if not restored_math and not restored_parentheses and not tables_at:
        return fallback
    output = []
    for i, line in enumerate(lines):
        output.extend(tables_at[i])
        text = "".join(span["text"] for span in line if id(span) not in table_spans)
        if text.strip():
            output.append(text.strip())
    output.extend(tables_at[len(lines)])
    return "\n".join(output)


def _ocr_text_key(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).casefold().split())


def get_page_thumbnails(
    file_path: Path, pages: list[int], dpi: int = PDF_LOADER_DPI
) -> List[str]:
    """Get PNG data URLs for pages in the PDF file.

    Args:
        file_path (Path): path to the image file
        page_number (list[int]): list of page numbers to extract

    Returns:
        list[str]: list of page thumbnails
    """

    img: Image.Image
    suffix = file_path.suffix.lower()
    assert suffix == ".pdf", "This function only supports PDF files."
    try:
        import fitz
    except ImportError:
        raise ImportError("Please install PyMuPDF: 'pip install PyMuPDF'")

    output_imgs = []
    with fitz.open(file_path) as doc:
        for page_number in pages:
            page = doc.load_page(page_number)
            pm = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", [pm.width, pm.height], pm.samples)
            output_imgs.append(convert_image_to_base64(img))

    return output_imgs


def convert_image_to_base64(img: Image.Image) -> str:
    # convert the image into base64
    img_bytes = BytesIO()
    img.save(img_bytes, format="PNG")
    img_base64 = base64.b64encode(img_bytes.getvalue()).decode("utf-8")
    img_base64 = f"data:image/png;base64,{img_base64}"

    return img_base64


class PDFThumbnailReader(PDFReader):
    """PDF parser with thumbnail for each page."""

    def __init__(self) -> None:
        """
        Initialize PDFReader.
        """
        super().__init__(return_full_document=False)

    def load_data(
        self,
        file: Path,
        extra_info: Optional[Dict] = None,
        fs: Optional[AbstractFileSystem] = None,
    ) -> List[Document]:
        """Extract the text layer, with local OCR for scans and embedded images."""
        import fitz

        file = Path(file)
        documents = super().load_data(file, extra_info, fs)
        text_documents = []
        with fitz.open(file) as pdf:
            for page, doc in zip(pdf, documents):
                text = doc.text.strip()
                if text:
                    text = _native_text_with_layout(page, text)
                    regions = [
                        fitz.Rect(image["bbox"]) * page.rotation_matrix & page.rect
                        for image in page.get_image_info()
                        if min(image["width"], image["height"]) >= 24
                    ]
                else:
                    regions = [None]

                seen = set()
                native_key = _ocr_text_key(text)
                lines = []
                for region in regions:
                    if region is not None and region.is_empty:
                        continue
                    raster = page.get_pixmap(dpi=200, clip=region).tobytes("png")
                    for line in read_image_text(raster):
                        key = _ocr_text_key(line)
                        if key and key not in native_key and key not in seen:
                            seen.add(key)
                            lines.append(line)
                if text or lines:
                    text_documents.append(
                        Document(
                            text="\n".join(filter(None, [text, *lines])),
                            metadata={**doc.metadata, "page_label": page.number + 1},
                        )
                    )

        if not text_documents:
            raise ValueError(f"No readable text found in {file.name}.")

        page_numbers = [doc.metadata["page_label"] for doc in text_documents]
        page_thumbnails = get_page_thumbnails(file, [p - 1 for p in page_numbers])

        text_documents.extend(
            [
                Document(
                    text="Page thumbnail",
                    metadata={
                        **(extra_info or {}),
                        "image_origin": page_thumbnail,
                        "type": "thumbnail",
                        "page_label": page_number,
                    },
                )
                for (page_thumbnail, page_number) in zip(page_thumbnails, page_numbers)
            ]
        )

        return text_documents
