"""Turn uploaded evidence into text the agents can read."""
import io
import zipfile
import re

MAX_CHARS = 200_000

ALLOWED_EXT = {".pdf", ".txt", ".csv", ".log", ".md", ".json", ".xml", ".xlsx", ".xlsm",
               ".docx", ".png", ".jpg", ".jpeg", ".eml"}


def extract(raw: bytes, filename: str) -> tuple[str, str]:
    """Return (text, note)."""
    name = filename.lower()
    try:
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            pages = []
            for i, p in enumerate(reader.pages):
                pages.append(f"[page {i+1}]\n{p.extract_text() or ''}")
            text = "\n".join(pages)
            note = f"PDF, {len(reader.pages)} pages"
            if len(text.strip()) < 20 * max(1, len(reader.pages)):
                note += " (little text found - may be scanned; OCR not enabled)"
        elif name.endswith((".xlsx", ".xlsm")):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            parts = []
            for ws in wb.worksheets:
                parts.append(f"[sheet {ws.title}]")
                for r in ws.iter_rows(values_only=True):
                    if any(v is not None for v in r):
                        parts.append(" | ".join("" if v is None else str(v) for v in r))
            text, note = "\n".join(parts), f"Workbook, {len(wb.worksheets)} sheets"
        elif name.endswith(".docx"):
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
            xml = re.sub(r"</w:p>", "\n", xml)
            text, note = re.sub(r"<[^>]+>", "", xml), "Word document"
        elif name.endswith((".png", ".jpg", ".jpeg")):
            return "", "Image stored; text not extracted (OCR not enabled)"
        else:
            text, note = raw.decode("utf-8-sig", errors="replace"), "Text"
    except Exception as e:  # noqa: BLE001 - bad files should not break uploads
        return "", f"Could not read file: {type(e).__name__}"
    if len(text) > MAX_CHARS:
        text, note = text[:MAX_CHARS], note + f" (cut to {MAX_CHARS} chars)"
    return text, note
