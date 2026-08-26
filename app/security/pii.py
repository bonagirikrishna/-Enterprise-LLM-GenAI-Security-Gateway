"""PII / PHI detection and redaction using Microsoft Presidio.

Adds custom PHI recognizers (medical record numbers, health insurance
IDs, ICD-10 codes) on top of Presidio's built-in entities
(PERSON, EMAIL_ADDRESS, PHONE_NUMBER, US_SSN, CREDIT_CARD, ...).
"""
from __future__ import annotations

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# --- Custom PHI recognizers ------------------------------------------------

MRN_PATTERN = Pattern(
    name="medical_record_number",
    regex=r"\b(?:MRN|M\.?R\.?N\.?)[-: ]*\d{5,10}\b",
    # Keep the labeled MRN intact instead of letting generic numeric
    # recognizers (for example, bank-account numbers) win an overlap.
    score=1.0,
)
HEALTH_PLAN_PATTERN = Pattern(
    name="health_insurance_id",
    regex=r"\b(?:HICN|H\.?I\.?C\.?N\.?|Member\sID)[-: ]*[A-Z0-9]{6,15}\b",
    score=0.80,
)
ICD10_PATTERN = Pattern(
    name="icd10_code",
    regex=r"\b[A-Z]\d{2}(?:\.\d{1,2})?\b",
    score=0.55,
)


def _build_analyzer(languages: list[str] | None = None) -> AnalyzerEngine:
    languages = languages or ["en"]
    provider = NlpEngineProvider()  # uses default spaCy model en_core_web_lg
    nlp_engine = provider.create_engine()
    engine = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=languages)

    engine.registry.add_recognizer(
        PatternRecognizer(
            supported_entity="MEDICAL_RECORD_NUMBER",
            patterns=[MRN_PATTERN],
        )
    )
    engine.registry.add_recognizer(
        PatternRecognizer(
            supported_entity="HEALTH_INSURANCE_ID",
            patterns=[HEALTH_PLAN_PATTERN],
        )
    )
    engine.registry.add_recognizer(
        PatternRecognizer(
            supported_entity="ICD10_CODE",
            patterns=[ICD10_PATTERN],
        )
    )
    return engine


class PIIScrubber:
    """Detects PII/PHI and replaces each value with a <ENTITY_TYPE> placeholder."""

    def __init__(self, languages: list[str] | None = None):
        self.languages = languages or ["en"]
        self.analyzer = _build_analyzer(self.languages)
        self.anonymizer = AnonymizerEngine()

    def scrub(self, text: str) -> tuple[str, dict[str, int]]:
        """Returns (redacted_text, entity_type -> occurrence_count)."""
        results = self.analyzer.analyze(text=text, language=self.languages[0])
        # Presidio can label ordinary temporal words such as "quarterly" as a
        # DATE_TIME entity. Those words are not identifying information and
        # redacting them makes otherwise clean prompts unusable.
        results = [result for result in results if result.entity_type != "DATE_TIME"]
        if not results:
            return text, {}

        # One custom operator per entity type -> "<ENTITY_TYPE>" placeholder
        operators = {
            entity_type: OperatorConfig(
                "custom",
                {"lambda": (lambda value, et=entity_type: f"<{et}>")},
            )
            for entity_type in {r.entity_type for r in results}
        }
        anonymized = self.anonymizer.anonymize(
            text=text, analyzer_results=results, operators=operators
        )

        counts: dict[str, int] = {}
        for r in results:
            counts[r.entity_type] = counts.get(r.entity_type, 0) + 1
        return anonymized.text, counts
