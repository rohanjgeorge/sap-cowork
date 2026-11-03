"""Application document conversion; no model calls or storage paths."""

from io import BytesIO
import re

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


def to_docx(artifact):
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    for edge in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, edge, Inches(0.8))
    document.styles["Normal"].font.name = "Calibri"
    document.styles["Normal"].font.size = Pt(11)
    for name in ("Title", "Heading 1", "Heading 2", "Heading 3"):
        document.styles[name].font.color.rgb = RGBColor(0, 0, 0)
        document.styles[name].font.underline = False
    # Some Word templates carry a paragraph border in the Title style.
    for root in (document.element, document.styles.element):
        for border in root.xpath(".//w:pBdr"):
            border.getparent().remove(border)
    table = None
    for line in artifact.content.splitlines():
        if line.startswith("|") and line.rstrip().endswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in cells):
                continue
            if table is None:
                table = document.add_table(rows=0, cols=len(cells))
                table.style = "Table Grid"
                table.autofit = False
                widths = (
                    [0.75, 0.95, 0.9, 2.4, 1.9]
                    if cells[0] == "Version" and len(cells) == 5
                    else [6.9 / len(cells)] * len(cells)
                )
                for column, width in zip(table.columns, widths):
                    column.width = Inches(width)
            if len(cells) == len(table.columns):
                header = len(table.rows) == 0
                row = table.add_row()
                if header:
                    repeat = OxmlElement("w:tblHeader")
                    row._tr.get_or_add_trPr().append(repeat)
                for index, (cell, text) in enumerate(zip(row.cells, cells)):
                    cell.width = table.columns[index].width
                    cell.text = text
                    if header:
                        shading = OxmlElement("w:shd")
                        shading.set(qn("w:fill"), "E8ECF0")
                        cell._tc.get_or_add_tcPr().append(shading)
                    for paragraph in cell.paragraphs:
                        paragraph.paragraph_format.space_after = Pt(4)
                        paragraph.paragraph_format.space_before = Pt(4)
                        for run in paragraph.runs:
                            run.font.size = Pt(10)
                            run.bold = header
                continue
        table = None
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            level = len(heading[1])
            document.add_paragraph(heading[2], "Title" if level == 1 else f"Heading {min(level - 1, 3)}")
        elif line.strip() and not line.startswith("```"):
            bullet = line.startswith("- ")
            paragraph = document.add_paragraph(style="List Bullet" if bullet else "Normal")
            text = line[2:] if bullet else line.lstrip("> ")
            for part in re.split(r"(\*\*.*?\*\*|`[^`]+`)", text):
                if part.startswith("**") and part.endswith("**"):
                    paragraph.add_run(part[2:-2]).bold = True
                elif part.startswith("`") and part.endswith("`"):
                    paragraph.add_run(part[1:-1]).font.name = "Consolas"
                else:
                    paragraph.add_run(part)
    if artifact.recommendations:
        document.add_heading("Recommended changes pending confirmation", 1)
        for recommendation in artifact.recommendations:
            document.add_paragraph(recommendation)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def from_docx(data):
    document = Document(BytesIO(data))
    # Preserve document order, including tables, for offline round trips.
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    lines = []
    for child in document.element.body:
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, document)
            text = paragraph.text
            style = paragraph.style.name
            if style == "Title":
                text = "# " + text
            elif style.startswith("Heading ") and style[-1].isdigit():
                text = "#" * (int(style[-1]) + 1) + " " + text
            lines.append(text)
        elif child.tag.endswith("}tbl"):
            table = Table(child, document)
            for index, row in enumerate(table.rows):
                lines.append("| " + " | ".join(c.text for c in row.cells) + " |")
                if index == 0:
                    lines.append("| " + " | ".join("---" for _ in row.cells) + " |")
    return "\n".join(lines)
