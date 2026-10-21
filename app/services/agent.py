from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app.parsers import DocumentRouter
from app.schemas import AuditTrail, BillRecord, ChargeDetails, ExtractionResult, FinancialAttributes, ParsedDocument
from app.services.extraction import Extractor
from app.services.matcher import BillMatcher
from app.services.normalization import Normalizer
from app.services.validation import Validator


class ShippingBillAgent:
    def __init__(self) -> None:
        self.router = DocumentRouter()
        self.extractor = Extractor()
        self.normalizer = Normalizer()
        self.validator = Validator()
        self.matcher = BillMatcher()

    def process(self, input_path: str | Path, accounting_entity: str, existing_bills: list[BillRecord] | None = None, public_url: str | None = None, attachment_urls: dict[str, str] | None = None) -> list[BillRecord]:
        parsed = self.router.parse(input_path, public_url=public_url, attachment_urls=attachment_urls)
        extracted = self._extract_recursive(parsed)
        records = self._to_records(extracted, accounting_entity)
        duplicates = self.validator.duplicate_keys(records)
        for record in records:
            if (record.document_info.reference_no, record.charge_details.charge_item, record.charge_details.amount, record.charge_details.currency) in duplicates:
                record.audit_trail.validations.append("Duplicate charge detected in current input")
                record.operation = "PENDING_REVIEW"
            self._decide(record, existing_bills or [])
        return records

    def _extract_recursive(self, document: ParsedDocument) -> list[tuple[ExtractionResult, list[str]]]:
        extracted = [(self.extractor.extract(document.text, document.source), [document.source])]
        for attachment in document.attachments:
            extracted.extend(self._extract_recursive(attachment))
        return extracted

    def _to_records(self, extracted: list[tuple[ExtractionResult, list[str]]], entity: str) -> list[BillRecord]:
        records: list[BillRecord] = []
        for result, sources in extracted:
            document_records: list[BillRecord] = []
            for charge in result.charges:
                normal_charge = ChargeDetails(
                    raw_charge_item=charge.raw_charge_item,
                    charge_item=self.normalizer.charge_name(charge.raw_charge_item),
                    quantity=charge.quantity,
                    unit_price=charge.unit_price,
                    amount=charge.amount,
                    currency=self.normalizer.currency(charge.currency),
                    payment_term=self.normalizer.payment_term(charge.payment_term),
                )
                posting = self._posting_type(result.transaction_party.issuer, result.transaction_party.recipient, entity, charge.charge_direction)
                record = BillRecord(
                    operation="CREATE",
                    document_info=result.document_info,
                    transaction_party=result.transaction_party,
                    charge_details=normal_charge,
                    financial_attributes=FinancialAttributes(accounting_entity=entity, posting_type=posting),
                    audit_trail=AuditTrail(source_files=sources, evidence=charge.evidence, ai_reasoning=["Extracted from source and normalized by deterministic rules"]),
                )
                record.audit_trail.validations.extend(self.validator.validate(record))
                if record.audit_trail.validations:
                    record.operation = "PENDING_REVIEW"
                document_records.append(record)
                records.append(record)
            self._validate_declared_total(result.declared_total, document_records)
        return records

    @staticmethod
    def _posting_type(issuer: str | None, recipient: str | None, entity: str, charge_direction: str | None = None) -> str | None:
        if not entity:
            return None
        entity_lower = entity.casefold()
        is_issuer = bool(issuer and issuer.casefold() == entity_lower)
        is_recipient = bool(recipient and recipient.casefold() == entity_lower)
        if charge_direction == "RECEIVABLE" and is_issuer:
            return "AR"
        if charge_direction == "PAYABLE" and is_recipient:
            return "AP"
        if charge_direction is None:
            if is_issuer:
                return "AR"
            if is_recipient:
                return "AP"
        return None

    @staticmethod
    def _validate_declared_total(declared_total, records: list[BillRecord]) -> None:
        if declared_total is None or not records or any(record.charge_details.amount is None for record in records):
            return
        extracted_total = sum((record.charge_details.amount for record in records), start=0)
        if abs(extracted_total - declared_total) > 0.02:
            for record in records:
                record.operation = "PENDING_REVIEW"
                record.audit_trail.validations.append(f"Charge sum {extracted_total} conflicts with declared document total {declared_total}")

    def _decide(self, record: BillRecord, existing: list[BillRecord]) -> None:
        if record.operation == "PENDING_REVIEW":
            return
        matches = self.matcher.find(record, existing)
        record.audit_trail.match_candidates = self.matcher.candidate_summary(matches)
        if not matches:
            record.audit_trail.ai_reasoning.append("No existing bill matched; create a new charge record")
            return
        if len(matches) > 1 and matches[0].score == matches[1].score:
            record.operation = "PENDING_REVIEW"
            record.audit_trail.validations.append("Ambiguous existing-bill match")
            return
        previous = matches[0].record
        changes = self._diff(previous, record)
        if not changes:
            record.operation = "NO_CHANGE"
            self._inherit_missing(previous, record)
            record.audit_trail.ai_reasoning.append(f"Matched existing bill by {matches[0].rule}; no explicit field changes")
        else:
            record.operation = "UPDATE"
            self._inherit_missing(previous, record)
            record.audit_trail.ai_reasoning.append(f"Matched existing bill by {matches[0].rule}; changed fields: {', '.join(changes)}")

    @staticmethod
    def _diff(previous: BillRecord, incoming: BillRecord) -> list[str]:
        fields = ("raw_charge_item", "charge_item", "quantity", "unit_price", "amount", "currency", "payment_term")
        return [field for field in fields if getattr(previous.charge_details, field) != getattr(incoming.charge_details, field) and getattr(incoming.charge_details, field) is not None]

    @staticmethod
    def _inherit_missing(previous: BillRecord, incoming: BillRecord) -> None:
        """Keep existing values when the source did not explicitly provide a replacement."""
        for section in ("document_info", "transaction_party", "charge_details", "financial_attributes"):
            prior = getattr(previous, section)
            target = getattr(incoming, section)
            for field in type(target).model_fields:
                if field == "accounting_entity":
                    continue
                if getattr(target, field) is None:
                    setattr(target, field, getattr(prior, field))
