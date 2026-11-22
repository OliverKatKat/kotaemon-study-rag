import unicodedata
from io import BytesIO
from pathlib import Path

from llama_index.core.readers.base import BaseReader
from PIL import Image, UnidentifiedImageError

from kotaemon.base import Document

from .utils.image_ocr import read_image_text

DRAWING = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
MATH = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
COMPAT = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
PRESENTATION = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def _format_math(element) -> str:
    """Read Office Math without flattening fractions, scripts or delimiters."""
    if element is None:
        return ""
    if element.tag == MATH + "t":
        return unicodedata.normalize("NFKC", element.text or "")
    if element.tag == MATH + "f":
        numerator = _format_math(element.find(MATH + "num"))
        denominator = _format_math(element.find(MATH + "den"))
        return f"({numerator})/({denominator})"
    if element.tag in (MATH + "sSup", MATH + "sSub", MATH + "sSubSup"):
        base = _format_math(element.find(MATH + "e"))
        if (subscript := element.find(MATH + "sub")) is not None:
            base += f"_({_format_math(subscript)})"
        if (superscript := element.find(MATH + "sup")) is not None:
            base += f"^({_format_math(superscript)})"
        return base
    if element.tag == MATH + "d":
        properties = element.find(MATH + "dPr")
        delimiters = (
            {child.tag: child.get(MATH + "val") for child in properties}
            if properties is not None
            else {}
        )
        opening = delimiters.get(MATH + "begChr", "(")
        closing = delimiters.get(MATH + "endChr", ")")
        separator = delimiters.get(MATH + "sepChr", "|")
        terms = (separator or "").join(
            _format_math(child) for child in element.findall(MATH + "e")
        )
        return f"{opening or ''}{terms}{closing or ''}"
    return "".join(_format_math(child) for child in element)


def _text_with_math(body) -> str:
    paragraphs = []
    for paragraph in body.findall(DRAWING + "p"):
        parts = []
        for child in paragraph:
            if child.tag == DRAWING + "br":
                parts.append("\n")
            elif child.tag in (DRAWING + "r", DRAWING + "fld"):
                parts.append(child.findtext(DRAWING + "t", ""))
            else:
                parts.extend(_format_math(math) for math in child.iter(MATH + "oMath"))
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs).strip()


class PptxReader(BaseReader):
    """Extract editable and raster text, preserving slide boundaries."""

    def load_data(
        self, file_path: Path, extra_info: dict | None = None, **kwargs
    ) -> list[Document]:
        from pptx import Presentation

        file_path = Path(file_path)
        presentation = Presentation(str(file_path))
        metadata = {
            "file_name": file_path.name,
            "file_path": str(file_path.resolve()),
            **(extra_info or {}),
        }
        documents = []
        image_text: dict[str, tuple[str, ...]] = {}
        for number, slide in enumerate(presentation.slides, 1):
            title = slide.shapes.title
            blocks = list(self._read_shapes(slide.shapes, image_text))
            if blocks:
                documents.append(
                    Document(
                        text="\n\n".join(blocks),
                        metadata={
                            **metadata,
                            "page_label": number,
                            "section": title.text.strip() if title is not None else "",
                        },
                    )
                )
        if not documents:
            raise ValueError(f"No readable text found in {file_path.name}.")
        return documents

    def _read_shapes(self, shapes, image_text):
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        from pptx.shapes.picture import Picture

        by_element = {shape._element: shape for shape in shapes}
        for element in shapes._spTree:
            shape = by_element.get(element)
            if shape is None:
                # Office wraps shapes containing native equations in AlternateContent.
                choice = element.find(COMPAT + "Choice")
                if choice is not None:
                    for body in choice.iter(PRESENTATION + "txBody"):
                        if text := _text_with_math(body):
                            yield text
                continue
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                yield from self._read_shapes(shape.shapes, image_text)
            elif shape.has_table:
                yield "\n".join(
                    " | ".join(cell.text for cell in row.cells)
                    for row in shape.table.rows
                )
            elif shape.has_text_frame:
                body = element.find(PRESENTATION + "txBody")
                if (
                    body is not None
                    and next(body.iter(MATH + "oMath"), None) is not None
                ):
                    text = _text_with_math(body)
                else:
                    text = shape.text.strip()
                if text:
                    yield text
            elif isinstance(shape, Picture):
                image = shape.image
                if image.sha1 not in image_text:
                    try:
                        with Image.open(BytesIO(image.blob)) as picture:
                            if min(picture.size) < 24:
                                continue
                            with BytesIO() as buffer:
                                picture.convert("RGB").save(buffer, format="PNG")
                                raster = buffer.getvalue()
                    except (UnidentifiedImageError, OSError):
                        # Ignore vector images that Pillow cannot rasterize.
                        continue
                    image_text[image.sha1] = read_image_text(raster, group_labels=True)
                yield from image_text[image.sha1]
