"""Prompt-injection detection.

Layered approach:
1. Weighted regex heuristics for known injection families
   (ignore-previous-instructions, DAN jailbreaks, system-prompt extraction,
   role-play overrides, obfuscated payloads, ...).
2. Optional Rebuff vector-DB layer (enabled via GW_REBUFF_ENABLED=true).
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# (weight, rule name, regex) — weight contributes to the 0..1 score
RULES: list[tuple[float, str, str]] = [
    (1.0, "ignore_previous_instructions",
     r"\bignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|above|prior|earlier|old)\s+(?:instructions?|prompts?|messages?|context|system\s+prompt)\b"),
    (1.0, "disregard_instructions",
     r"\bdisregard\s+(?:all\s+|the\s+|any\s+)?(?:previous|above|prior|earlier|system)?\s*instructions?\b"),
    (1.0, "forget_rules",
     r"\bforget\s+(?:all\s+|your\s+|any\s+)?(?:rules|instructions?|guidelines?|prompts?|training)\b"),
    (1.0, "reveal_system_prompt",
     r"\b(?:reveal|show|output|print|display|repeat|tell\s+me)\s+(?:your|the|this|its)\s+(?:full\s+|complete\s+|initial\s+)?(?:system\s+)?(?:prompt|instructions?|system\s+message)\b"),
    (0.9, "dan_or_jailbreak",
     r"\b(?:dan\b|jailbreak\b|unfiltered\b|developer\s+mode\b|do\s+anything\s+now\b)"),
    (0.9, "new_instruction_set",
     r"\b(?:here\s+are|these\s+are|now\s+you\s+will\s+follow|from\s+now\s+on|you\s+must\s+now)\s+(?:your\s+|the\s+|new\s+)?instructions?\b"),
    (0.85, "override_constraints",
     r"\b(?:override|bypass|circumvent|ignore)\s+(?:your\s+|the\s+|all\s+)?(?:safety|ethical|moral|content\s+policy|restrictions?|filter|guardrails?|guidelines?)\b"),
    (0.8, "pretend_role",
     r"\bpretend\s+(?:you|we|to\s+be)\s+(?:are|were|to\s+be)?\b"),
    (0.8, "act_as_role",
     r"\bact\s+as\s+(?:if\s+you\s+were|a|an|though\s+you\s+are)\b"),
    (0.75, "no_restrictions",
     r"\b(?:with\s+no|without|you\s+have\s+no|no\s+more)\s+(?:rules|restrictions|limits|filters|guardrails|safety\s+guidelines)\b"),
    (0.7, "encoded_payload",
     r"\b(?:base64|hex|rot13)\s*(?:decode|encoded|obfuscated)"),
    (0.6, "simulation_request",
     r"\b(?:simulate|simulation|role[- ]?play|virtual\s+machine|sandbox|developer\s+console)\b"),
    (0.6, "access_system_data",
     r"\b(?:access|retrieve|read)\s+(?:your\s+|the\s+)?(?:system|internal|hidden)\s+(?:data|files|configuration|memory)\b"),
]


class HeuristicInjectionDetector:
    def __init__(self) -> None:
        self._compiled = [
            (weight, name, re.compile(pattern, re.IGNORECASE))
            for weight, name, pattern in RULES
        ]

    def score(self, text: str) -> tuple[float, list[str]]:
        """Returns (score 0..1, list of matched rule names)."""
        total = 0.0
        matched: list[str] = []
        for weight, name, pattern in self._compiled:
            if pattern.search(text):
                total += weight
                matched.append(name)
        return min(total, 1.0), matched


class RebuffDetector:
    """Optional vector-DB-based detector (needs OpenAI + Pinecone)."""

    def __init__(self, settings) -> None:
        from rebuff import RebuffSdk  # lazy import keeps install optional

        self._sdk = RebuffSdk(
            openai_apikey=settings.openai_api_key_for_rebuff,
            openai_model=settings.openai_model_for_rebuff,
            pinecone_apikey=settings.pinecone_api_key,
            pinecone_environment=settings.pinecone_environment,
            pinecone_index_name=settings.pinecone_index_name,
        )

    def detect(self, text: str) -> tuple[float, bool]:
        res = self._sdk.detect_injection(text)
        score = float(getattr(res, "injection_score", getattr(res, "score", 0.0)))
        flagged = bool(getattr(res, "injection_detected", getattr(res, "injection", False)))
        return score, flagged


class InjectionDetector:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.heuristic = HeuristicInjectionDetector()
        self._rebuff = None
        if settings.rebuff_enabled:
            try:
                self._rebuff = RebuffDetector(settings)
                logger.info("Rebuff injection layer enabled")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Rebuff unavailable, using heuristics only: %s", exc)

    def detect(self, text: str) -> tuple[float, list[str]]:
        score, rules = self.heuristic.score(text)
        if self._rebuff is not None:
            try:
                r_score, flagged = self._rebuff.detect(text)
                score = max(score, r_score)
                if flagged:
                    rules.append("rebuff")
            except Exception as exc:  # noqa: BLE001
                logger.debug("Rebuff detection failed: %s", exc)
        return min(score, 1.0), rules