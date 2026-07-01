#!/usr/bin/env python3
"""Correction/positive/guardrail pattern detection for claude-reflect.

Cross-platform compatible (Windows, macOS, Linux).
Part of the reflect_utils split (#8); reflect_utils re-exports these names.
"""
from __future__ import annotations

import re
from typing import NamedTuple


# Explicit marker patterns (highest confidence)
EXPLICIT_PATTERNS = [
    (r"remember:", "remember:", 0.90, 120),  # pattern, name, confidence, decay_days
]


# Positive feedback patterns
POSITIVE_PATTERNS = [
    (r"perfect!|exactly right|that's exactly", "perfect", 0.70, 90),
    (r"that's what I wanted|great approach", "great-approach", 0.70, 90),
    (r"keep doing this|love it|excellent|nailed it", "keep-doing", 0.70, 90),
]


# Correction patterns (conservative set to minimize false positives)
# Format: (regex_pattern, pattern_name, is_strong)
#
# DESIGN NOTES (ADR-0001 — recall at capture, precision at /reflect):
# - Capture is a wide RECALL net. These openers over-capture on purpose; the
#   /reflect agent judges reusability inline, where a wrong call costs one glance.
# - No capture-time precision tables (FALSE_POSITIVE / NON_CORRECTION /
#   FORWARD_PIVOT) and no subprocess semantic pass — a precision miss here would
#   be a permanent, unreviewable drop, which the product promise forbids.
# - Non-English corrections: CJK recall openers below + explicit "remember:" in
#   any language; finer language precision is the inline /reflect judgment's job.
# - The only capture-time filters are cheap structural guards: the length cap and
#   should_include_message (drops system content, not user intent).
#
CORRECTION_PATTERNS = [
    (r"^no[,. ]+", "no,", True),  # Starts with "no," - common correction opener
    (r"^don't\b|^do not\b", "don't", True),  # Starts with don't/do not
    (r"^stop\b|^never\b", "stop/never", True),  # Starts with stop/never
    (r"that's (wrong|incorrect)|that is (wrong|incorrect)", "that's-wrong", True),
    (r"^actually[,. ]", "actually", False),  # Starts with "actually"
    (r"^I meant\b|^I said\b", "I-meant/said", True),  # Clarification
    (r"^I told you\b|^I already told\b", "I-told-you", True),  # Higher confidence
    (r"use .{1,30} not\b", "use-X-not-Y", True),  # "use X not Y" - limited gap
]


# Guardrail patterns - "don't do X unless" constraints (highest confidence for corrections)
# These detect user frustrations about Claude making unwanted changes
# Format: (regex_pattern, pattern_name, confidence, decay_days)
GUARDRAIL_PATTERNS = [
    (r"don't (?:add|include|create) .{1,40} unless", "dont-unless-asked", 0.90, 120),
    (r"only (?:change|modify|edit|touch) what I (?:asked|requested|said)", "only-what-asked", 0.90, 120),
    (r"stop (?:refactoring|changing|modifying|editing) (?:unrelated|other|surrounding)", "stop-unrelated", 0.90, 120),
    (r"don't (?:over-engineer|add extra|be too|make unnecessary)", "dont-over-engineer", 0.85, 90),
    (r"don't (?:refactor|reorganize|restructure) (?:unless|without)", "dont-refactor-unless", 0.85, 90),
    (r"leave .{1,30} (?:alone|unchanged|as is)", "leave-alone", 0.85, 90),
    (r"don't (?:add|include) (?:comments|docstrings|type hints|annotations) (?:unless|to code)", "dont-add-annotations", 0.85, 90),
    (r"(?:minimal|minimum|only necessary) changes", "minimal-changes", 0.80, 90),
]


# CJK correction patterns (parallel to English CORRECTION_PATTERNS)
# These detect explicit corrections in CJK languages
# Format: (regex_pattern, pattern_name, is_strong)
CJK_CORRECTION_PATTERNS = [
    # Japanese
    (r"^いや[、,.\s]|^いや違", "iya", True),       # いや、〜 / いや違う - "no, ..."
    (r"^違う[、，,.\s！!。]|^ちがう[、,.\s]", "chigau", True),  # 違う、〜 - "wrong, ..."
    (r"そうじゃなく[てけ]|そっちじゃなく[てけ]", "souja-nakute", True),  # "not that"
    (r"間違[いえっ]て", "machigatte", True),       # 間違ってる - "it's wrong"
    (r"じゃなくて.{0,30}にして", "janakute-nishite", True),  # 〜じゃなくて〜にして
    (r"^やめて[。！!]?\s*$", "yamete", True),      # やめて - "stop"
    (r"^そうじゃない", "souja-nai", True),          # そうじゃない - "that's not right"
    (r"って言った[のよでじゃ]", "tte-itta", True),   # って言ったのに - "I told you"
    # Chinese
    (r"^不是[，,. ]", "bushi", True),              # 不是、〜 - "no, ..."
    (r"^错了|^錯了", "cuole", True),               # 错了 - "wrong"
    (r"不要.{0,20}要", "buyao-yao", True),         # 不要X要Y - "don't X, use Y"
    # Korean
    (r"^아니[,. ]", "ani", True),                  # 아니, - "no, ..."
    (r"틀렸", "teullyeoss", True),                 # 틀렸 - "wrong"
]


# Maximum prompt length for live capture (UserPromptSubmit hook)
# Prompts longer than this are almost certainly system content, not user corrections.
# Exception: explicit "remember:" markers are always processed regardless of length.
MAX_CAPTURE_PROMPT_LENGTH = 500


# Maximum message length for weak patterns (structural heuristic)
# Long messages are more likely to be context/tasks than corrections
MAX_WEAK_PATTERN_LENGTH = 150


# Length→confidence structural signal (see _adjust_confidence_for_length).
# Short messages read as direct corrections and are boosted; long ones read as
# context/tasks and are penalized.
SHORT_CORRECTION_MAX_LENGTH = 80   # below this a message counts as "short" (boosted)
MID_MESSAGE_MAX_LENGTH = 150       # above this (English only) a mild penalty applies
LONG_MESSAGE_MAX_LENGTH = 300      # above this a stronger penalty applies

SHORT_CONFIDENCE_BOOST = 0.10      # added when short
MID_CONFIDENCE_PENALTY = 0.10      # subtracted when mid-length (English only)
LONG_CONFIDENCE_PENALTY = 0.15     # subtracted when long

CONFIDENCE_BOOST_CAP = 0.90        # ceiling after the short boost
MID_CONFIDENCE_FLOOR = 0.55        # floor after the mid-length penalty
LONG_CONFIDENCE_FLOOR = 0.50       # floor after the long penalty


def _adjust_confidence_for_length(
    confidence: float,
    text_length: int,
    penalize_mid: bool = True,
) -> float:
    """Nudge a correction's confidence by message length (structural signal).

    Short messages read as direct corrections (boost); long ones read as
    context/tasks (penalty). Shared by the CJK and English correction branches so
    the shape lives in one place. The English branch is a superset: it also
    penalizes mid-length messages (``penalize_mid=True``), which the CJK branch
    historically did not — so CJK passes ``penalize_mid=False`` to keep behavior
    identical to the pre-refactor code.
    """
    if text_length < SHORT_CORRECTION_MAX_LENGTH:
        return min(CONFIDENCE_BOOST_CAP, confidence + SHORT_CONFIDENCE_BOOST)
    if text_length > LONG_MESSAGE_MAX_LENGTH:
        return max(LONG_CONFIDENCE_FLOOR, confidence - LONG_CONFIDENCE_PENALTY)
    if penalize_mid and text_length > MID_MESSAGE_MAX_LENGTH:
        return max(MID_CONFIDENCE_FLOOR, confidence - MID_CONFIDENCE_PENALTY)
    return confidence


class Detection(NamedTuple):
    """Structured result of detect_patterns.

    Index/unpack-compatible with the legacy 5-tuple
    (type, patterns, confidence, sentiment, decay_days), so existing
    ``a, b, c, d, e = detect_patterns(...)`` and ``result[0]`` call sites keep
    working while new code can use field access.
    """
    type: str | None
    patterns: str
    confidence: float
    sentiment: str
    decay_days: int


# Sentinel for "no detection" — reused so every miss returns the same value.
_NO_DETECTION = Detection(None, "", 0.0, "correction", 90)


def detect_patterns(text: str) -> Detection:
    """
    Detect patterns in text and return classification.

    Returns:
        A Detection(type, patterns, confidence, sentiment, decay_days).
        type: "explicit", "positive", "auto", "guardrail", or None
        patterns: Space-separated pattern names
        confidence: 0.0 to 1.0
        sentiment: "correction" or "positive"
        decay_days: Number of days until decay
    """
    # Too short to be actionable (e.g. "OK", "好", "yes")
    # CJK characters carry more meaning per char, so use a lower threshold
    stripped = text.strip()
    has_cjk = bool(re.search(r'[\u3000-\u9fff\uf900-\ufaff\uac00-\ud7af]', stripped))
    short_threshold = 2 if has_cjk else 4
    if len(stripped) <= short_threshold:
        return _NO_DETECTION

    # Check for explicit "remember:" - always highest priority
    for pattern, name, confidence, decay in EXPLICIT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return Detection("explicit", name, confidence, "correction", decay)

    # Check for guardrail patterns - "don't do X unless" constraints
    # These are high-confidence corrections about unwanted behavior
    for pattern, name, confidence, decay in GUARDRAIL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return Detection("guardrail", name, confidence, "correction", decay)

    # Check for positive patterns
    matched_positive = []
    for pattern, name, confidence, decay in POSITIVE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            matched_positive.append(name)

    if matched_positive:
        return Detection("positive", " ".join(matched_positive), 0.70, "positive", 90)

    # Skip long messages for weak patterns (likely task requests)
    text_length = len(text)

    # Check for CJK correction patterns (language-specific)
    # Use stripped text for anchor patterns (^/$) to handle leading/trailing whitespace
    matched_cjk = []
    cjk_strong = False
    for pattern, name, is_strong in CJK_CORRECTION_PATTERNS:
        if re.search(pattern, stripped):
            matched_cjk.append(name)
            if is_strong:
                cjk_strong = True

    if matched_cjk:
        confidence = 0.75 if cjk_strong else 0.60
        decay_days = 90 if cjk_strong else 60
        # CJK branch never penalized mid-length messages — keep that (penalize_mid=False).
        confidence = _adjust_confidence_for_length(
            confidence, text_length, penalize_mid=False
        )
        return Detection("auto", " ".join(matched_cjk), confidence, "correction", decay_days)

    # Check for English correction patterns
    matched_corrections = []
    pattern_count = 0
    has_strong_pattern = False
    has_i_told_you = False

    for pattern, name, is_strong in CORRECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            # Skip weak patterns in long messages
            if not is_strong and text_length > MAX_WEAK_PATTERN_LENGTH:
                continue
            matched_corrections.append(name)
            pattern_count += 1
            if is_strong:
                has_strong_pattern = True
            if name == "I-told-you":
                has_i_told_you = True

    if matched_corrections:
        # Calculate confidence based on pattern count, type, and length
        if has_i_told_you:
            confidence = 0.85
            decay_days = 120
        elif pattern_count >= 3:
            confidence = 0.85
            decay_days = 120
        elif pattern_count >= 2:
            confidence = 0.75
            decay_days = 90
        elif has_strong_pattern:
            confidence = 0.70
            decay_days = 60
        else:
            confidence = 0.55  # Reduced for weak single patterns
            decay_days = 45

        # Adjust confidence based on message length (structural signal)
        confidence = _adjust_confidence_for_length(confidence, text_length)

        return Detection("auto", " ".join(matched_corrections), confidence, "correction", decay_days)

    return _NO_DETECTION


def is_correction_candidate(text: str) -> bool:
    """Recall predicate: does this message carry a correction signal?

    The single source of truth shared by live capture and ``--corrections-only``
    session extraction, so the two paths cannot diverge (ADR-0001). Delegates to
    detect_patterns, so every correction/guardrail/explicit opener — English or
    CJK — counts, and positive-only feedback does not.
    """
    detection = detect_patterns(text)
    return detection.type is not None and detection.sentiment == "correction"


def should_include_message(text: str) -> bool:
    """Check if a message should be included in learning detection.

    Filters out system content like XML tags, JSON, tool results, and
    session continuations that should never be treated as user corrections.

    Used by both session file extraction and live capture (UserPromptSubmit hook).
    """
    # Skip empty lines
    if not text.strip():
        return False

    # Skip lines starting with certain patterns
    skip_patterns = [
        r"^<",              # XML tags (<task-notification>, <system-reminder>, etc.)
        r"^\[",             # Brackets
        r"^\{",             # JSON
        r"tool_result",
        r"tool_use_id",
        r"<command-",
        r"<task-notification>",
        r"<system-reminder>",
        r"This session is being continued",
        r"^Analysis:",
        r"^\*\*",           # Bold text
        r"^   -",           # Indented lists
    ]

    for pattern in skip_patterns:
        if re.search(pattern, text):
            return False

    return True


# Backward-compatible alias
_should_include_message = should_include_message
