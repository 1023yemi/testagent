from __future__ import annotations

import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.schemas import DocumentInfo, ExtractedCharge, ExtractionResult, SourceEvidence, TransactionParty


CHARGE_TERMS = r"(?:handling(?:\s+fee)?|h/d\s+fee|doc(?:umentation)?\s+fee|thc|terminal handling|trucking(?:\s+fee)?|customs(?:\s+fee)?|storage(?:\s+fee)?|ocean freight|freight(?:\s+fee)?)"
AMOUNT = r"(?P<amount>-?[\d,]+(?:\.\d{1,2})?)"
CURRENCY = r"(?P<currency>USD|CNY|RMB|EUR|GBP|HKD|SGD|JPY|AUD|CAD)"


class Extractor:
    """Schema-first extractor.

    The deterministic extraction makes the app runnable offline. With an API key,
    the optional LangChain path can improve unstructured document coverage while
    still passing through the same validators and decision engine.
    """

    def extract(self, text: str, source: str) -> ExtractionResult:
        result = self._extract_with_rules(text, source)
        if os.getenv("OPENAI_API_KEY"):
            try:
                llm_result = self._extract_with_langchain(text, source)
                if llm_result.charges:
                    return llm_result
            except Exception:
                # The audit path remains deterministic when a remote model fails.
                pass
        return result

    def _extract_with_rules(self, text: str, source: str) -> ExtractionResult:
        info = DocumentInfo(
            document_type=self._capture(text, r"\b(Debit Note|Credit Note|Invoice)\b"),
            reference_no=self._capture(text, r"(?:D/C\s*(?:No\.)?|Debit Note|Credit Note|Invoice|(?:Reference|Ref(?:erence)?)\s*No)\s*[:#.]?\s*([A-Z]{1,8}[- ]?\d{4,}|[A-Z0-9-]{6,})"),
            document_date=self._date(text),
            bill_of_lading_no=self._capture(text, r"(?:(?:MASTER\s+)?(?:MBL|B/L|Bill of Lading))\s*(?:No\.?|#)?\s*[:_]?\s*([A-Z]{3,6}\d{6,})") or self._capture(text, r"\b([A-Z]{4,6}\d{6,})\b"),
            booking_no=self._capture(text, r"(?:Booking)\s*(?:No\.?|#)?\s*[:_]?\s*([A-Z0-9-]{6,})"),
            container_no=self._capture(text, r"(?:Container|CNTR)\s*(?:No\.?|#)?\s*[:_]?\s*([A-Z]{4}\d{7})"),
        )
        parties = TransactionParty(
            issuer=self._capture(text, r"(?:Issuer|From|Seller|Shipper)\s*:\s*([^\n]{2,80})"),
            recipient=self._capture(text, r"(?:Recipient|To|Buyer|Consignee)\s*:\s*([^\n]{2,80})"),
        )
        charges: list[ExtractedCharge] = []
        document_currency = self._capture(text, r"(?:CURRENCY|CUR)\s*[:.]?\s*(USD|CNY|RMB|EUR|GBP|HKD|SGD|JPY|AUD|CAD)")
        document_payment = self._capture(text, r"(?:TERMS?|PAYMENT)\s*[:.]?\s*(PP|CC|PREPAID|COLLECT)")
        direction = self._direction(text)
        pattern = re.compile(rf"(?P<charge>{CHARGE_TERMS}).{{0,45}}?{CURRENCY}\s*{AMOUNT}(?:\s*(?P<payment>PP|CC|PREPAID|COLLECT))?", re.I)
        for match in pattern.finditer(text):
            amount = self._decimal(match.group("amount"))
            evidence = SourceEvidence(source=source, text=match.group(0), confidence=0.78)
            charges.append(ExtractedCharge(raw_charge_item=match.group("charge"), amount=amount, currency=match.group("currency"), payment_term=match.group("payment"), charge_direction=direction, evidence={"charge_details": [evidence]}))
        # Tables extracted from PDF often put currency in the header instead of on
        # each line, e.g. "HANDLING CHARGE - 65.00 1.00 C 65.00".
        table_pattern = re.compile(
            r"^(?P<charge>(?:\d+\s+)?[A-Z][A-Z'&/ .+-]{2,}?)\s+-\s+(?P<rate>[\d,]+(?:\.\d+)?)\s+(?P<qty>[\d,]+(?:\.\d+)?)\s+[A-Z]\s+(?P<amount>[\d,]+(?:\.\d+)?)\s*$",
            re.M,
        )
        for match in table_pattern.finditer(text):
            evidence = SourceEvidence(source=source, text=match.group(0), confidence=0.88)
            charges.append(ExtractedCharge(
                raw_charge_item=match.group("charge").strip(),
                unit_price=self._decimal(match.group("rate")),
                quantity=self._decimal(match.group("qty")),
                amount=self._decimal(match.group("amount")),
                currency=document_currency,
                payment_term=document_payment,
                charge_direction=direction,
                evidence={"charge_details": [evidence]},
            ))
        # Arrival-notice style documents commonly present a single fee as a row
        # under "CHARGES CUR AMOUNT" and use a non-standard fee description.
        generic_pattern = re.compile(r"^(?P<charge>[A-Za-z][^\n]{2,90}?)\s+(?P<currency>USD|CNY|RMB|EUR|GBP|HKD|SGD|JPY|AUD|CAD)\s+(?P<amount>[\d,]+(?:\.\d+)?)\s*$", re.M)
        for match in generic_pattern.finditer(text):
            raw = match.group("charge").strip()
            if raw.upper().startswith(("TOTAL", "CURRENCY", "PAID")):
                continue
            evidence = SourceEvidence(source=source, text=match.group(0), confidence=0.72)
            charges.append(ExtractedCharge(raw_charge_item=raw, amount=self._decimal(match.group("amount")), currency=match.group("currency"), payment_term=document_payment, charge_direction=direction, evidence={"charge_details": [evidence]}))
        return ExtractionResult(document_info=info, transaction_party=parties, charges=charges, declared_total=self._declared_total(text))

    def _extract_with_langchain(self, text: str, source: str) -> ExtractionResult:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        prompt = ChatPromptTemplate.from_messages([
            ("system", "Extract only facts explicitly present in the shipping billing text. Unknown values must be null. Return every charge as a separate record."),
            ("human", "Source: {source}\n\nDocument:\n{text}"),
        ])
        chain = prompt | ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0).with_structured_output(ExtractionResult)
        return chain.invoke({"source": source, "text": text})

    @staticmethod
    def _capture(text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, re.I)
        if not match:
            return None
        return (match.group(1) if match.lastindex else match.group(0)).strip(" :#_\t")

    @staticmethod
    def _date(text: str):
        match = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).date()
            except ValueError:
                return None
        match = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b", text)
        if match:
            try:
                return datetime(int(match.group(3)), int(match.group(1)), int(match.group(2))).date()
            except ValueError:
                return None
        return None

    @staticmethod
    def _decimal(value: str | None) -> Decimal | None:
        try:
            return Decimal(value.replace(",", "")) if value else None
        except InvalidOperation:
            return None

    def _declared_total(self, text: str) -> Decimal | None:
        match = re.search(r"(?:TOTAL\s+AMOUNT|GRAND\s+TOTAL)\s*[:.]?\s*([\d,]+(?:\.\d+)?)", text, re.I)
        return self._decimal(match.group(1)) if match else None

    @staticmethod
    def _direction(text: str) -> str | None:
        normalized = text.upper()
        if re.search(r"(?:CHARGES?|AMOUNT|BALANCE)\s+(?:TO\s+BE\s+)?PAID|DUE\s+TO", normalized):
            return "PAYABLE"
        if re.search(r"(?:AMOUNT|BALANCE)\s+RECEIVABLE|TO\s+COLLECT", normalized):
            return "RECEIVABLE"
        return None
