"""Repeatable, offline acceptance harness for shipping-bill extraction."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.services.extraction import Extractor


@dataclass(frozen=True)
class HarnessCase:
    name: str
    text: str
    expected_charge_count: int
    expected_amounts: tuple[Decimal, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HarnessResult:
    name: str
    passed: bool
    details: str


class ExtractionHarness:
    """Checks deterministic extraction without requiring an LLM or OCR network call."""

    def __init__(self, extractor: Extractor | None = None) -> None:
        self.extractor = extractor or Extractor()

    def run(self, case: HarnessCase) -> HarnessResult:
        result = self.extractor.extract(case.text, f"harness:{case.name}")
        amounts = tuple(charge.amount for charge in result.charges)
        passed = len(result.charges) == case.expected_charge_count and amounts == case.expected_amounts
        return HarnessResult(case.name, passed, f"charges={len(result.charges)}, amounts={amounts}")

    def run_all(self, cases: list[HarnessCase]) -> list[HarnessResult]:
        return [self.run(case) for case in cases]
