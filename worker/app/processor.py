import time
from collections import deque
from typing import Any, Dict, Tuple

from .config import MAX_RATE_PER_SEC, EXTRACTION_MODE
from .logger import logger


class RetryableError(Exception):
    pass


class FatalError(Exception):
    pass


class RateLimiter:
    def __init__(self, max_per_sec: int):
        self.max_per_sec = max_per_sec
        self.events = deque()

    def check(self):
        if self.max_per_sec <= 0:
            return
        now = time.time()
        while self.events and now - self.events[0] > 1:
            self.events.popleft()
        if len(self.events) >= self.max_per_sec:
            raise RetryableError("rate_limited")
        self.events.append(now)


rate_limiter = RateLimiter(MAX_RATE_PER_SEC)


def stage_ocr(text: str) -> str:
    # In this mock, OCR simply passes through, but we keep the hook for errors/timeouts.
    if "FAIL_OCR" in text:
        raise RetryableError("ocr_failed")
    return text


def extract_evidence(text: str) -> Tuple[Dict[str, Any], Dict[str, Any], list[str]]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    evidence: Dict[str, Any] = {}
    sources: Dict[str, Any] = {}
    missing: list[str] = []

    def find_line(patterns):
        for idx, line in enumerate(lines):
            for pat in patterns:
                if pat in line.lower():
                    return idx + 1, line
        return None, None

    # Diagnosis
    diag_line, diag_text = find_line(["osteoarthritis", "knee pain"])
    evidence["diagnosis"] = "osteoarthritis" if diag_line else None
    if diag_line:
        sources["diagnosis"] = {"line": diag_line, "text": diag_text}
    else:
        missing.append("diagnosis")

    # Conservative therapy: require PT; NSAIDs alone are insufficient
    pt_line, pt_text = find_line(["physical therapy", "pt"])
    nsaid_line, nsaid_text = find_line(["nsaid", "nsaids"])

    def is_pt_negated(text: str) -> bool:
        lowered = text.lower()
        return any(
            phrase in lowered
            for phrase in [
                "no documented physical therapy",
                "no physical therapy",
                "without physical therapy",
                "did not do physical therapy",
            ]
        )

    pt_ok = bool(pt_line and not is_pt_negated(pt_text or ""))
    if pt_ok:
        evidence["conservative_therapy"] = {"attempted": True, "detail": pt_text}
        sources["conservative_therapy"] = {"line": pt_line, "text": pt_text}
    else:
        # Record NSAID detail if present, but it does not satisfy PT requirement
        detail_text = pt_text if pt_text else (nsaid_text if nsaid_line else None)
        evidence["conservative_therapy"] = {"attempted": False, "detail": detail_text}
        if detail_text:
            sources["conservative_therapy"] = {"line": pt_line or nsaid_line, "text": detail_text}
        missing.append("conservative_therapy")

    # Imaging
    imaging_line, imaging_text = find_line(["x-ray", "xray", "mri", "ct", "imaging"])
    if imaging_line:
        evidence["imaging_evidence"] = True
        sources["imaging_evidence"] = {"line": imaging_line, "text": imaging_text}
    else:
        evidence["imaging_evidence"] = False
        missing.append("imaging_evidence")

    # Functional limitation
    func_line, func_text = find_line(["difficulty", "cannot", "limited", "adl", "activities of daily living"])
    if func_line:
        evidence["functional_limitation"] = True
        sources["functional_limitation"] = {"line": func_line, "text": func_text}
    else:
        evidence["functional_limitation"] = False
        missing.append("functional_limitation")

    # Basic schema validation
    for key in ["diagnosis", "conservative_therapy", "imaging_evidence", "functional_limitation"]:
        if key not in evidence:
            raise RetryableError("schema_missing_field")

    return evidence, sources, missing


def evaluate_policy(evidence: Dict[str, Any], missing: list[str]) -> Tuple[str, str, list[str]]:
    decision = "APPROVE"
    explanation_parts = []

    if evidence.get("diagnosis") != "osteoarthritis":
        decision = "NEEDS_MORE_INFO"
        if "diagnosis" not in missing:
            missing.append("diagnosis")

    therapy = evidence.get("conservative_therapy") or {}
    therapy_attempted = therapy.get("attempted", False)
    if not therapy_attempted:
        decision = "NEEDS_MORE_INFO"
        if "conservative_therapy" not in missing:
            missing.append("conservative_therapy")
        explanation_parts.append("Need physical therapy documentation.")

    if not evidence.get("imaging_evidence"):
        decision = "NEEDS_MORE_INFO"
        if "imaging_evidence" not in missing:
            missing.append("imaging_evidence")
        explanation_parts.append("Imaging evidence missing.")

    if not evidence.get("functional_limitation"):
        decision = "NEEDS_MORE_INFO"
        if "functional_limitation" not in missing:
            missing.append("functional_limitation")
        explanation_parts.append("Functional limitation affecting ADLs missing.")

    if decision == "APPROVE":
        explanation_parts.append("All required evidence present for TKA.")

    explanation = " ".join(explanation_parts) if explanation_parts else "Evidence evaluated."
    return decision, explanation, missing


def guardrails(evidence: Dict[str, Any], sources: Dict[str, Any]):
    # Require citation for each field present
    for key, value in evidence.items():
        if key == "conservative_therapy":
            # Only require citation if attempted is True
            if isinstance(value, dict) and value.get("attempted") is False:
                continue
        if value and key not in sources:
            raise RetryableError("missing_citation")
    # Basic type checks
    if not isinstance(sources, dict):
        raise RetryableError("invalid_sources")


def llm_extract(text: str) -> Tuple[Dict[str, Any], Dict[str, Any], list[str]]:
    # Placeholder LLM extractor: reuses heuristic extraction but can be swapped for real LLM.
    # Guardrail hook: simulate invalid output trigger
    if "FAIL_LLM" in text:
        raise RetryableError("llm_invalid_output")
    return extract_evidence(text)


def extract_with_guardrails(text: str) -> Tuple[Dict[str, Any], Dict[str, Any], list[str]]:
    if EXTRACTION_MODE.lower() == "hybrid":
        try:
            evidence, sources, missing = llm_extract(text)
            guardrails(evidence, sources)
            return evidence, sources, missing
        except RetryableError:
            logger.warn("LLM extraction failed, falling back to heuristics")
    evidence, sources, missing = extract_evidence(text)
    guardrails(evidence, sources)
    return evidence, sources, missing
