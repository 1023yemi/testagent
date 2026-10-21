from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


Operation = Literal["CREATE", "UPDATE", "NO_CHANGE", "PENDING_REVIEW"]


class SourceEvidence(BaseModel):
    source: str
    text: str
    confidence: float = 1.0


class DocumentInfo(BaseModel):
    document_type: Optional[str] = None
    reference_no: Optional[str] = None
    document_date: Optional[date] = None
    bill_of_lading_no: Optional[str] = None
    booking_no: Optional[str] = None
    container_no: Optional[str] = None


class TransactionParty(BaseModel):
    issuer: Optional[str] = None
    recipient: Optional[str] = None


class ChargeDetails(BaseModel):
    raw_charge_item: Optional[str] = None
    charge_item: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    payment_term: Optional[str] = None


class FinancialAttributes(BaseModel):
    accounting_entity: str
    posting_type: Optional[Literal["AR", "AP"]] = None


class AuditTrail(BaseModel):
    source_files: list[str] = Field(default_factory=list)
    evidence: dict[str, list[SourceEvidence]] = Field(default_factory=dict)
    validations: list[str] = Field(default_factory=list)
    ai_reasoning: list[str] = Field(default_factory=list)
    match_candidates: list[dict[str, Any]] = Field(default_factory=list)


class BillRecord(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: float})

    operation: Operation
    document_info: DocumentInfo
    transaction_party: TransactionParty
    charge_details: ChargeDetails
    financial_attributes: FinancialAttributes
    audit_trail: AuditTrail


class ParsedDocument(BaseModel):
    source: str
    kind: str
    text: str
    tables: list[list[list[str]]] = Field(default_factory=list)
    attachments: list["ParsedDocument"] = Field(default_factory=list)


class ExtractedCharge(BaseModel):
    raw_charge_item: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    payment_term: Optional[str] = None
    charge_direction: Optional[Literal["PAYABLE", "RECEIVABLE"]] = None
    evidence: dict[str, list[SourceEvidence]] = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    document_info: DocumentInfo = Field(default_factory=DocumentInfo)
    transaction_party: TransactionParty = Field(default_factory=TransactionParty)
    charges: list[ExtractedCharge] = Field(default_factory=list)
    declared_total: Optional[Decimal] = None

