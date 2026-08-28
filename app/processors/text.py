"""Text/CSV processor (Phase 4) — authors print-ready PDFs for text files.

A text file has no pages of its own, so this processor AUTHORS the layout
(multi-format plan §0, answer 4):

    TXT → monospace text, word-wrapped, paginated
    CSV → a bordered grid with the header row repeated on every page

reportlab draws both onto the shared page (base.page_size_pt). reportlab
is a Python library — unlike LibreOffice it runs INSIDE the test suite, so
these conversions are exercised for real, not mocked.

Encoding: text has no magic bytes (detection trusts the extension), so
decoding is verified here: UTF-16 (only with a BOM, which carries the byte
order) → UTF-8 → Windows-1252. A file that decodes as none of those is a
binary file wearing a text-file name and fails with a clear error instead
of printing mojibake.

Limits (paper + memory guards on the ≤4 GB PC): TXT caps at MAX_TXT_PAGES;
CSV caps rows and columns — both print an explicit "truncated" notice.

Known limitation: the built-in Courier font covers Latin scripts; CJK or
emoji print as boxes (registering a Unicode TTF is a v2 idea).
"""

import csv
import io
import logging
import math
from pathlib import Path

from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdfcanvas

from app.processors.base import ConversionError, page_size_pt

logger = logging.getLogger(__name__)

FONT = "Courier"
FONT_BOLD = "Courier-Bold"
FONT_SIZE = 9.5
LINE_HEIGHT = 12
CELL_PADDING = 3
MARGIN_PT = 54  # 0.75" — text pages want breathing room on both sides
MAX_TXT_PAGES = 100
CSV_MAX_ROWS = 1000  # rendered rows INCLUDING the header row
CSV_MAX_COLS = 30

# Monospace: every character occupies the width of an "M".
CHAR_W = stringWidth("M", FONT, FONT_SIZE)


def decode_text(data: bytes) -> str:
    """Bytes → text, with the no-mojibake guarantee described above."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")  # BOM carries the byte order
    for encoding in ("utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ConversionError(
        "This text file does not decode as text (tried UTF-8, UTF-16 and "
        "Windows-1252) — it may be a binary file with a text-file name."
    )


def wrap_line(line: str, max_chars: int) -> list[str]:
    """Word-wrap one logical line into chunks of at most max_chars.

    Breaks at spaces when it can; a single word longer than a whole line
    is hard-split rather than allowed to overflow the page.
    """
    if len(line) <= max_chars:
        return [line]
    chunks: list[str] = []
    rest = line
    while len(rest) > max_chars:
        cut = rest.rfind(" ", 0, max_chars + 1)
        if cut <= 0:
            cut = max_chars  # no space to break at: hard-split the word
        chunks.append(rest[:cut].rstrip(" "))
        rest = rest[cut:].lstrip(" ")
    chunks.append(rest)
    return chunks


def sniff_dialect(sample: str):
    """Detect , ; tab | delimiters; fall back to plain comma-separated."""
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def grid_columns(rows: list[list[str]], avail_w: float) -> list[float]:
    """Column widths in points for a grid that must fit `avail_w`.

    Each width covers its widest cell (a monster cell is capped so it
    can't hog the page) PLUS the cell padding on both sides — the same
    accounting _clip_cell uses — then the whole grid is scaled down
    proportionally when it exceeds the printable width.
    """
    column_count = max((len(row) for row in rows), default=1)
    char_counts = [1] * column_count
    for row in rows:
        for index, cell in enumerate(row):
            char_counts[index] = max(char_counts[index], min(len(cell), 60))
    widths = [count * CHAR_W + 2 * CELL_PADDING for count in char_counts]
    if sum(widths) > avail_w:
        factor = avail_w / sum(widths)
        widths = [width * factor for width in widths]
    return widths


def _clip_cell(cell: str, column_w: float) -> str:
    # The 1e-9 absorbs binary-float noise in the width math (e.g. a cell
    # that is exactly 2.0 characters wide must not truncate to 1).
    max_chars = int((column_w - 2 * CELL_PADDING) / CHAR_W + 1e-9)
    if len(cell) <= max_chars:
        return cell
    return cell[: max(0, max_chars - 3)] + "..."


def _render_txt(text: str, canvas: pdfcanvas.Canvas, page_w: float, page_h: float) -> int:
    """Monospace, wrapped, paginated. Returns the page count."""
    max_chars = int((page_w - 2 * MARGIN_PT) / CHAR_W)
    lines_per_page = int((page_h - 2 * MARGIN_PT) // LINE_HEIGHT)

    logical = (
        text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
        .replace("\f", "\n")
        .split("\n")
    )
    wrapped: list[str] = []
    for line in logical:
        wrapped.extend(wrap_line(line, max_chars))

    total_pages = math.ceil(len(wrapped) / lines_per_page)
    truncated = total_pages > MAX_TXT_PAGES
    pages = min(total_pages, MAX_TXT_PAGES)

    for page in range(pages):
        # setFont belongs to the page being drawn — anything after the
        # final showPage would touch a new page and reportlab would emit
        # it as a blank trailing page.
        canvas.setFont(FONT, FONT_SIZE)
        chunk = wrapped[page * lines_per_page : (page + 1) * lines_per_page]
        if truncated and page == pages - 1:
            chunk[-1] = "[truncated — the file was longer than the print limit]"
        y = page_h - MARGIN_PT - FONT_SIZE
        for line in chunk:
            canvas.drawString(MARGIN_PT, y, line)
            y -= LINE_HEIGHT
        canvas.showPage()
    return pages


def _render_csv(
    rows: list[list[str]], canvas: pdfcanvas.Canvas, page_w: float, page_h: float
) -> int:
    """Bordered grid, header repeated per page, caps with a notice."""
    original_rows = len(rows)
    original_cols = max(len(row) for row in rows)

    truncated_cols = original_cols > CSV_MAX_COLS
    if truncated_cols:
        rows = [row[:CSV_MAX_COLS] for row in rows]
    column_count = max(len(row) for row in rows)
    rows = [row + [""] * (column_count - len(row)) for row in rows]  # pad ragged rows

    truncated_rows = original_rows > CSV_MAX_ROWS
    if truncated_rows:
        rows = rows[:CSV_MAX_ROWS]

    notes = []
    if truncated_rows:
        notes.append(f"[truncated — showing the first {CSV_MAX_ROWS} of "
                     f"{original_rows} rows]")
    if truncated_cols:
        notes.append(f"[truncated — showing the first {CSV_MAX_COLS} of "
                     f"{original_cols} columns]")
    note_space = LINE_HEIGHT * (len(notes) + 1)  # +1: never touch the bottom margin

    header, data = rows[0], rows[1:]
    column_widths = grid_columns(rows, page_w - 2 * MARGIN_PT)
    grid_w = sum(column_widths)
    row_h = LINE_HEIGHT + 2 * CELL_PADDING
    rows_per_page = max(1, int((page_h - 2 * MARGIN_PT - note_space) // row_h))
    data_per_page = rows_per_page - 1  # the header occupies a slot on every page
    pages = max(1, math.ceil(len(data) / data_per_page))

    for page in range(pages):
        y_top = page_h - MARGIN_PT
        page_rows = [header] + data[page * data_per_page : (page + 1) * data_per_page]
        grid_h = row_h * len(page_rows)

        canvas.setLineWidth(0.4)
        for index in range(len(page_rows) + 1):  # horizontal rules
            y = y_top - index * row_h
            canvas.line(MARGIN_PT, y, MARGIN_PT + grid_w, y)
        x = MARGIN_PT
        for width in [*column_widths]:  # vertical rules
            x += width
            canvas.line(x, y_top - grid_h, x, y_top)

        for row_index, row in enumerate(page_rows):
            canvas.setFont(FONT_BOLD if row_index == 0 else FONT, FONT_SIZE)
            y = y_top - (row_index + 1) * row_h + CELL_PADDING
            x = MARGIN_PT
            for col_index, cell in enumerate(row):
                canvas.drawString(
                    x + CELL_PADDING, y, _clip_cell(cell, column_widths[col_index])
                )
                x += column_widths[col_index]

        if page == pages - 1:
            canvas.setFont(FONT, FONT_SIZE)
            y = y_top - grid_h - LINE_HEIGHT
            for note in notes:
                canvas.drawString(MARGIN_PT, y, note)
                y -= LINE_HEIGHT

        canvas.showPage()
    return pages


class TextProcessor:
    def available(self) -> bool:
        # reportlab is a hard dependency (requirements.txt) — always on.
        return True

    def process(self, src: Path, out_dir: Path) -> Path:
        """Render a TXT/CSV file into the print-ready PDF the engine gets."""
        pdf_path = out_dir / f"{src.stem}.pdf"
        data = src.read_bytes()
        if not data.strip():
            raise ConversionError("The text file is empty — nothing to print.")

        text = decode_text(data)
        page_w, page_h = page_size_pt()
        # pageCompression off: the drawn text stays visible in the bytes,
        # which is how the tests (and a plain text editor) can verify output.
        document = pdfcanvas.Canvas(str(pdf_path), pagesize=(page_w, page_h), pageCompression=0)
        try:
            if src.suffix.lower() == ".csv":
                rows = [
                    row
                    for row in csv.reader(io.StringIO(text), sniff_dialect(text[:4096]))
                    if any(cell.strip() for cell in row)  # blank lines are noise
                ]
                if not rows:
                    raise ConversionError("The CSV file contains no rows to print.")
                pages = _render_csv(rows, document, page_w, page_h)
            else:
                pages = _render_txt(text, document, page_w, page_h)
        except ConversionError:
            raise
        except Exception as exc:
            raise ConversionError(f"Could not render the text as PDF: {exc}") from exc
        document.save()

        logger.info(
            "rendered %s -> %s (%d page(s))", src.name, pdf_path.name, pages
        )
        return pdf_path


# Stateless → one shared instance for every job.
TEXT_PROCESSOR = TextProcessor()
