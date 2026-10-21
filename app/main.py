from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.schemas import BillRecord
from app.services import ShippingBillAgent


def read_existing(path: str | None) -> list[BillRecord]:
    if not path:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [BillRecord.model_validate(item) for item in payload]


def main() -> None:
    parser = argparse.ArgumentParser(description="Shipping billing agent")
    parser.add_argument("--input", required=True)
    parser.add_argument("--existing-bills")
    parser.add_argument("--accounting-entity", required=True)
    parser.add_argument("--public-url", help="Public URL for the specified OCR API")
    parser.add_argument("--ocr-url-map", help="JSON mapping of EML attachment filename to OCR-accessible URL")
    parser.add_argument("--output", default="output/result.json")
    args = parser.parse_args()

    attachment_urls = json.loads(Path(args.ocr_url_map).read_text(encoding="utf-8")) if args.ocr_url_map else None
    records = ShippingBillAgent().process(args.input, args.accounting_entity, read_existing(args.existing_bills), args.public_url, attachment_urls)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps([record.model_dump(mode="json") for record in records], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(records)} record(s) to {destination}")


if __name__ == "__main__":
    main()
