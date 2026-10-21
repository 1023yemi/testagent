"""Conversion adapters for legacy Word .doc files.

The binary .doc format cannot be faithfully parsed by python-docx. Prefer a
locally installed LibreOffice converter, which preserves document tables. An
Antiword fallback obtains text when LibreOffice is unavailable. The final OLE
fallback in ``router.py`` keeps the source readable instead of silently losing
the document.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class LegacyDocConverter:
    @staticmethod
    def to_docx(payload: bytes) -> bytes | None:
        soffice = shutil.which("soffice")
        if not soffice:
            return None
        with tempfile.TemporaryDirectory(prefix="shipping-bill-doc-") as directory:
            root = Path(directory)
            source = root / "source.doc"
            source.write_bytes(payload)
            result = subprocess.run(
                [soffice, "--headless", "--convert-to", "docx", "--outdir", str(root), str(source)],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            converted = root / "source.docx"
            if result.returncode == 0 and converted.exists():
                return converted.read_bytes()
        return None

    @staticmethod
    def to_text(payload: bytes) -> str | None:
        antiword = shutil.which("antiword")
        if not antiword:
            return None
        with tempfile.NamedTemporaryFile(prefix="shipping-bill-doc-", suffix=".doc", delete=False) as handle:
            source = Path(handle.name)
            handle.write(payload)
        try:
            result = subprocess.run([antiword, str(source)], capture_output=True, text=True, timeout=60, check=False)
            return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
        finally:
            source.unlink(missing_ok=True)
