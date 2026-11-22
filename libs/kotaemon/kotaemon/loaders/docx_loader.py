import csv
import unicodedata
from io import BytesIO, StringIO
from pathlib import Path
from typing import List, Optional

from llama_index.core.readers.base import BaseReader
from PIL import Image, UnidentifiedImageError

from kotaemon.base import Document

from .utils.image_ocr import read_image_text


def _table_text(rows):
    buffer = StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue().strip()


def _table_chunks(rows):
    from llama_index.core.node_parser import TokenTextSplitter
    from llama_index.core.utils import get_tokenizer

    # Leave room for differences between our token estimate and embedding models.
    budget = 4096
    tokenize = get_tokenizer()
    table = _table_text(rows)
    if len(tokenize(table)) <= budget:
        if table:
            yield table
        return

    header = rows[:1] if len(tokenize(_table_text(rows[:1]))) <= budget // 2 else []
    splitter = TokenTextSplitter(chunk_size=budget // 4, chunk_overlap=0)
    group = header.copy()
    for row in rows[len(header) :]:
        if len(tokenize(_table_text([*header, row]))) <= budget:
            parts = [row]
        else:
            context = [
                cell if len(tokenize(cell)) <= budget // 8 else "" for cell in row
            ]
            if len(tokenize(_table_text([*header, context]))) > budget * 5 // 8:
                context = [""] * len(row)
            parts = []
            for column, cell in enumerate(row):
                if context[column]:
                    continue
                for text in splitter.split_text(cell):
                    part = context.copy()
                    part[column] = text
                    parts.append(part)
        for part in parts:
            if len(group) > len(header) and len(
                tokenize(_table_text([*group, part]))
            ) > budget:
                yield _table_text(group)
                group = header.copy()
            group.append(part)
    if len(group) > len(header):
        yield _table_text(group)


class DocxReader(BaseReader):
    """Read Word paragraphs by section and keep tables in document order."""

    def __init__(self, *args, **kwargs):
        try:
            import docx  # noqa
        except ImportError:
            raise ImportError(
                "docx is not installed. "
                "Please install it using `pip install python-docx`"
            )

    def load_data(
        self, file_path: Path, extra_info: Optional[dict] = None, **kwargs
    ) -> List[Document]:
        import docx
        from docx.text.paragraph import Paragraph

        file_path = Path(file_path).resolve()
        metadata = {
            "file_name": file_path.name,
            "file_path": str(file_path),
            **(extra_info or {}),
        }
        documents = []
        section = ""
        paragraphs = []
        image_text: dict[str, tuple[str, ...]] = {}

        def flush_paragraphs():
            if paragraphs:
                documents.append(
                    Document(
                        text="\n\n".join(paragraphs),
                        metadata={**metadata, "section": section},
                    )
                )
                paragraphs.clear()

        for block in docx.Document(str(file_path)).iter_inner_content():
            if isinstance(block, Paragraph):
                title = unicodedata.normalize("NFKC", block.text).strip()
                if title and block.style and block.style.style_id.startswith("Heading"):
                    flush_paragraphs()
                    section = title
                if text := self._paragraph_text(block, image_text).strip():
                    paragraphs.append(unicodedata.normalize("NFKC", text))
            else:
                flush_paragraphs()
                rows = []
                seen_cells = set()
                for row in block.rows:
                    cells = [""] * row.grid_cols_before
                    for cell in row.cells:
                        if cell._tc in seen_cells:
                            cells.append("")
                            continue
                        seen_cells.add(cell._tc)
                        cells.append(
                            "\n".join(
                                self._paragraph_text(paragraph, image_text)
                                for paragraph in cell.paragraphs
                            )
                        )
                    rows.append(cells + [""] * row.grid_cols_after)
                for table in _table_chunks(rows):
                    documents.append(
                        Document(
                            text=table,
                            metadata={
                                **metadata,
                                "section": section,
                                "table_origin": table,
                                "type": "table",
                            },
                            metadata_template="",
                        )
                    )

        flush_paragraphs()
        return documents

    @staticmethod
    def _paragraph_text(paragraph, image_text):
        from docx.drawing import Drawing
        from docx.oxml.ns import qn
        from docx.parts.image import ImagePart
        from docx.text.hyperlink import Hyperlink

        parts = []
        for inline in paragraph.iter_inner_content():
            runs = inline.runs if isinstance(inline, Hyperlink) else (inline,)
            for run in runs:
                for item in run.iter_inner_content():
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, Drawing):
                        for blip in item._drawing.xpath(".//a:blip"):
                            part = paragraph.part.related_parts.get(
                                blip.get(qn("r:embed"))
                            )
                            if not isinstance(part, ImagePart):
                                continue
                            if part.sha1 not in image_text:
                                image_text[part.sha1] = ()
                                try:
                                    with Image.open(BytesIO(part.blob)) as image:
                                        if min(image.size) < 24:
                                            continue
                                        buffer = BytesIO()
                                        image.convert("RGB").save(buffer, "PNG")
                                except (UnidentifiedImageError, OSError):
                                    continue
                                image_text[part.sha1] = read_image_text(buffer.getvalue())
                            if lines := image_text[part.sha1]:
                                parts.extend(("\n", "\n".join(lines), "\n"))
        return "".join(parts)
