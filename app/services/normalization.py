from __future__ import annotations

import json
import re
from pathlib import Path


class Normalizer:
    def __init__(self) -> None:
        rules_root = Path(__file__).parents[1] / "rules"
        self.mapping: dict[str, list[str]] = json.loads((rules_root / "charge_mapping.json").read_text(encoding="utf-8"))
        self.currency_codes = set(json.loads((rules_root / "currency_codes.json").read_text(encoding="utf-8")))

    def charge_name(self, raw: str | None) -> str | None:
        if not raw:
            return None
        simplified = re.sub(r"\s+", " ", raw.strip().lower())
        for standard, aliases in self.mapping.items():
            if simplified == standard or any(alias in simplified for alias in aliases):
                return standard.title()
        return raw.strip()

    def currency(self, raw: str | None) -> str | None:
        if not raw:
            return None
        code = raw.strip().upper().replace("$", "USD")
        if code == "RMB":
            code = "CNY"
        return code if code in self.currency_codes else None

    @staticmethod
    def payment_term(raw: str | None) -> str | None:
        if not raw:
            return None
        text = raw.strip().upper()
        if text in {"PP", "PREPAID", "PREPAID FREIGHT"}:
            return "PP"
        if text in {"CC", "COLLECT", "FREIGHT COLLECT"}:
            return "CC"
        return None
