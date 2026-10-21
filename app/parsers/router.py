from __future__ import annotations

import email
import io
import re
from email import policy
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

from app.parsers.ocr_client import OCRClient
from app.parsers.legacy_doc import LegacyDocConverter
from app.schemas import ParsedDocument


class DocumentRouter:
    def __init__(self, ocr_client: OCRClient | None = None) -> None:
        self.ocr_client = ocr_client or OCRClient()

    def parse(self, path: str | Path, public_url: str | None = None, attachment_urls: dict[str, str] | None = None) -> ParsedDocument:
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix == ".eml":
            return self._parse_eml(file_path, attachment_urls or {})
        if suffix in {".xlsx", ".xlsm"}:
            return self._parse_excel(file_path)
        if suffix == ".xls":
            return self._parse_xls(file_path)
        if suffix in {".docx"}:
            return self._parse_docx(file_path)
        if suffix == ".doc":
            return self._parse_doc(file_path)
        if suffix == ".pdf":
            return self._parse_pdf(file_path, public_url)
        if suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
            return self._parse_image(file_path, public_url)
        raise ValueError(f"Unsupported file type: {suffix}")

    def _parse_eml(self, path: Path, attachment_urls: dict[str, str]) -> ParsedDocument:
        message = email.message_from_bytes(path.read_bytes(), policy=policy.default)
        headers = "\n".join(f"{name}: {value}" for name, value in message.items())
        body: list[str] = []
        attachments: list[ParsedDocument] = []
        for part in message.walk():
            if part.is_multipart():
                continue
            disposition = part.get_content_disposition()
            filename = part.get_filename()
            if disposition == "attachment" or filename:
                payload = part.get_payload(decode=True) or b""
                name = filename or "attachment"
                attachments.append(self._parse_attachment(name, payload, attachment_urls.get(name)))
            elif part.get_content_type() == "text/plain":
                body.append(part.get_content())
        return ParsedDocument(source=str(path), kind="eml", text=headers + "\n\n" + "\n".join(body), attachments=attachments)

    def _parse_attachment(self, filename: str, payload: bytes, public_url: str | None = None) -> ParsedDocument:
        suffix = Path(filename).suffix.lower()
        if suffix in {".txt", ".csv"}:
            return ParsedDocument(source=filename, kind=suffix[1:], text=payload.decode(errors="replace"))
        if suffix == ".eml":
            message = email.message_from_bytes(payload, policy=policy.default)
            return ParsedDocument(source=filename, kind="eml", text="\n".join(f"{k}: {v}" for k, v in message.items()))
        if suffix in {".xlsx", ".xlsm"}:
            return self._parse_excel_stream(filename, payload)
        if suffix == ".xls":
            return self._parse_xls_stream(filename, payload)
        if suffix == ".docx":
            return self._parse_docx_stream(filename, payload)
        if suffix == ".doc":
            return self._parse_doc_stream(filename, payload)
        if suffix == ".pdf":
            try:
                text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(payload)).pages).strip()
                if not text and public_url:
                    text = self.ocr_client.to_text(self.ocr_client.extract(public_url))
                return ParsedDocument(source=filename, kind="pdf", text=text or "[PDF attachment requires OCR URL mapping]")
            except Exception as exc:
                if public_url:
                    return ParsedDocument(source=filename, kind="pdf", text=self.ocr_client.to_text(self.ocr_client.extract(public_url)))
                return ParsedDocument(source=filename, kind="pdf", text=f"[PDF needs OCR URL mapping: {exc}]")
        if suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
            if public_url:
                return ParsedDocument(source=filename, kind="image", text=self.ocr_client.to_text(self.ocr_client.extract(public_url)))
            return ParsedDocument(source=filename, kind="image", text="[Image attachment requires OCR URL mapping]")
        return ParsedDocument(source=filename, kind="binary", text="[Unsupported attachment; retained as source evidence]")

    def _parse_pdf(self, path: Path, public_url: str | None) -> ParsedDocument:
        text = ""
        try:
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages).strip()
        except Exception:
            pass
        if not text and public_url:
            text = self.ocr_client.to_text(self.ocr_client.extract(public_url))
        elif not text:
            text = "[No embedded PDF text. Supply --public-url to invoke OCR.]"
        return ParsedDocument(source=str(path), kind="pdf", text=text)

    def _parse_image(self, path: Path, public_url: str | None) -> ParsedDocument:
        if not public_url:
            return ParsedDocument(source=str(path), kind="image", text="[Image requires OCR. Supply --public-url accessible to OCR service.]")
        return ParsedDocument(source=str(path), kind="image", text=self.ocr_client.to_text(self.ocr_client.extract(public_url)))

    def _parse_excel(self, path: Path) -> ParsedDocument:
        return self._parse_excel_stream(str(path), path.read_bytes())

    def _parse_excel_stream(self, source: str, payload: bytes) -> ParsedDocument:
        book = load_workbook(io.BytesIO(payload), data_only=True, read_only=True)
        tables: list[list[list[str]]] = []
        lines: list[str] = []
        for sheet in book.worksheets:
            rows = [["" if value is None else str(value) for value in row] for row in sheet.iter_rows(values_only=True)]
            tables.append(rows)
            lines.append(f"[Sheet: {sheet.title}]\n" + "\n".join(" | ".join(row) for row in rows))
        return ParsedDocument(source=source, kind="excel", text="\n".join(lines), tables=tables)

    def _parse_xls(self, path: Path) -> ParsedDocument:
        return self._parse_xls_stream(str(path), path.read_bytes())

    @staticmethod
    def _parse_xls_stream(source: str, payload: bytes) -> ParsedDocument:
        try:
            import xlrd
        except ImportError as exc:
            raise RuntimeError("XLS support requires xlrd; install requirements.txt") from exc
        book = xlrd.open_workbook(file_contents=payload)
        tables: list[list[list[str]]] = []
        lines: list[str] = []
        for sheet in book.sheets():
            rows = [["" if value == "" else str(value) for value in sheet.row_values(index)] for index in range(sheet.nrows)]
            tables.append(rows)
            lines.append(f"[Sheet: {sheet.name}]\n" + "\n".join(" | ".join(row) for row in rows))
        return ParsedDocument(source=source, kind="excel", text="\n".join(lines), tables=tables)

    def _parse_docx(self, path: Path) -> ParsedDocument:
        return self._parse_docx_stream(str(path), path.read_bytes())

    def _parse_docx_stream(self, source: str, payload: bytes) -> ParsedDocument:
        doc = Document(io.BytesIO(payload))
        tables = [[[cell.text.strip() for cell in row.cells] for row in table.rows] for table in doc.tables]
        text = "\n".join(p.text for p in doc.paragraphs) + "\n" + "\n".join("\n".join(" | ".join(row) for row in table) for table in tables)
        return ParsedDocument(source=source, kind="word", text=text, tables=tables)

    def _parse_doc(self, path: Path) -> ParsedDocument:
        return self._parse_doc_stream(str(path), path.read_bytes())

    @staticmethod
    def _parse_doc_stream(source: str, payload: bytes) -> ParsedDocument:
        """Best-effort legacy .doc extraction without requiring Office automation.

        Word's binary format is not table-native to Python. We retain printable
        text for the Agent and expose it as single-column rows; callers can
        replace this adapter with a commercial converter if fidelity is needed.
        """
        converted = LegacyDocConverter.to_docx(payload)
        if converted:
            return DocumentRouter()._parse_docx_stream(source, converted)
        converted_text = LegacyDocConverter.to_text(payload)
        if converted_text:
            return ParsedDocument(source=source, kind="word", text=converted_text, tables=[[[line] for line in converted_text.splitlines()]])
        try:
            import olefile
        except ImportError as exc:
            raise RuntimeError("DOC support requires olefile; install requirements.txt") from exc
        if not olefile.isOleFile(io.BytesIO(payload)):
            raise ValueError("Invalid legacy .doc file")
        container = olefile.OleFileIO(io.BytesIO(payload))
        blobs = []
        for stream in ("WordDocument", "0Table", "1Table"):
            if container.exists(stream):
                blobs.append(container.openstream(stream).read())
        chunks: list[str] = []
        for blob in blobs:
            for encoding in ("utf-16le", "cp1252"):
                decoded = blob.decode(encoding, errors="ignore")
                chunks.extend(re.findall(r"[\u4e00-\u9fffA-Za-z0-9][\u4e00-\u9fffA-Za-z0-9 ,.:;()/_&+\-]{3,}", decoded))
        text = "\n".join(dict.fromkeys(part.strip() for part in chunks if part.strip()))
        return ParsedDocument(source=source, kind="word", text=text, tables=[[[line] for line in text.splitlines()]])
