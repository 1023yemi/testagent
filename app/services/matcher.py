from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.schemas import BillRecord


@dataclass
class Match:
    record: BillRecord
    rule: str
    score: int


class BillMatcher:
    def find(self, incoming: BillRecord, existing: list[BillRecord]) -> list[Match]:
        d, c = incoming.document_info, incoming.charge_details
        candidates: list[Match] = []
        for old in existing:
            od, oc = old.document_info, old.charge_details
            rule = None
            score = 0
            if d.reference_no and d.reference_no == od.reference_no and c.charge_item == oc.charge_item:
                rule, score = "reference_no + charge_item", 100
            elif d.bill_of_lading_no and d.bill_of_lading_no == od.bill_of_lading_no and c.charge_item == oc.charge_item and c.currency == oc.currency:
                rule, score = "bill_of_lading_no + charge_item + currency", 90
            elif d.booking_no and d.booking_no == od.booking_no and c.charge_item == oc.charge_item and c.currency == oc.currency:
                rule, score = "booking_no + charge_item + currency", 80
            elif self._container_party_date_amount(incoming, old):
                rule, score = "container + parties + date + amount", 70
            if rule:
                candidates.append(Match(old, rule, score))
        return sorted(candidates, key=lambda item: item.score, reverse=True)

    @staticmethod
    def _container_party_date_amount(left: BillRecord, right: BillRecord) -> bool:
        ld, rd = left.document_info, right.document_info
        lp, rp = left.transaction_party, right.transaction_party
        la, ra = left.charge_details.amount, right.charge_details.amount
        return bool(ld.container_no and ld.container_no == rd.container_no and lp == rp and ld.document_date == rd.document_date and la is not None and la == ra)

    @staticmethod
    def candidate_summary(matches: list[Match]) -> list[dict[str, Any]]:
        return [{"rule": match.rule, "score": match.score, "reference_no": match.record.document_info.reference_no} for match in matches]
