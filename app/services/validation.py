from __future__ import annotations

from collections import Counter
from decimal import Decimal

from app.schemas import BillRecord


class Validator:
    def validate(self, record: BillRecord) -> list[str]:
        errors: list[str] = []
        charge = record.charge_details
        if charge.amount is None:
            errors.append("Missing or non-numeric amount")
        elif charge.amount < Decimal("0"):
            errors.append("Negative amount requires manual review")
        if charge.currency is None:
            errors.append("Currency missing or not valid ISO 4217 code")
        if charge.quantity is not None and charge.unit_price is not None and charge.amount is not None:
            if abs(charge.quantity * charge.unit_price - charge.amount) > Decimal("0.02"):
                errors.append("Quantity × unit price does not equal amount")
        if record.document_info.reference_no is None and record.document_info.bill_of_lading_no is None and record.document_info.booking_no is None:
            errors.append("No stable document or shipment identifier")
        return errors

    @staticmethod
    def duplicate_keys(records: list[BillRecord]) -> set[tuple[str | None, str | None, Decimal | None, str | None]]:
        keys = [(r.document_info.reference_no, r.charge_details.charge_item, r.charge_details.amount, r.charge_details.currency) for r in records]
        counts = Counter(keys)
        return {key for key, count in counts.items() if count > 1}
