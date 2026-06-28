import re

FILLER_PHRASES = [
    "it's important to note",
    "it goes without saying",
    "at the end of the day",
    "in today's world",
    "this raises important questions",
    "it's worth noting",
    "in conclusion",
    "needless to say",
    "as we can see",
    "at its core",
    "the fact of the matter",
    "when all is said and done",
    "it's no secret that",
    "more often than not",
    "in the grand scheme of things",
    "it's fair to say",
    "building on this",
    "with that said",
    "to put it simply",
    "last but not least",
    "first and foremost",
    "on the other hand",
    "it's crucial to understand",
    "it's no surprise that",
]

# (regex pattern, human-readable label)
PARALLEL_REGEX_PATTERNS = [
    (r"it(?:’s| is) not just .+?,\s*it(?:’s| is)", "it’s not just..., it’s"),
    (r"not only .+? but also", "not only...but also"),
    (r"this isn['’]t about .+?\.\s+[Ii]t['’]s about", "this isn't about...it's about"),
    (r"whether .+ or .+", "whether...or"),
]


def _normalize(text: str) -> str:
    """Lowercase and normalize curly apostrophes to straight for matching."""
    return text.lower().replace("’", "'").replace("‘", "'")


def analyze(text: str) -> tuple[float, list[str]]:
    """
    Analyze text for AI-generation surface patterns.

    Returns:
        (rule_score, matched_patterns)
        rule_score: float 0.0–1.0
        matched_patterns: list of every matched phrase/pattern label

    Raises:
        ValueError: if text is under 40 words.
    """
    words = text.split()
    word_count = len(words)

    if word_count < 40:
        raise ValueError(
            "This content is too short for reliable analysis. "
            "Submit at least 40 words for a confident result."
        )

    matched_patterns: list[str] = []
    normalized = _normalize(text)

    # --- Em-dash frequency ---
    emdash_count = text.count("—")
    if emdash_count > 0:
        matched_patterns.extend(["—"] * emdash_count)
    emdash_score = min(1.0, (emdash_count / word_count) * 100 * 0.25)

    # --- Filler phrase density ---
    filler_count = 0
    for phrase in FILLER_PHRASES:
        occurrences = normalized.count(phrase)
        if occurrences > 0:
            filler_count += occurrences
            matched_patterns.extend([phrase] * occurrences)
    filler_density = (filler_count / word_count) * 100  # per 100 words

    # --- Base score ---
    base_score = min(1.0, (emdash_score * 0.25) + (filler_density * 0.75))

    # --- Parallel structure bonus (each hit adds 0.05, total capped at 1.0) ---
    parallel_bonus = 0.0

    # Regex-based patterns
    for pattern, label in PARALLEL_REGEX_PATTERNS:
        matches = re.findall(pattern, normalized, re.DOTALL)
        for _ in matches:
            parallel_bonus += 0.05
            matched_patterns.append(label)

    # 3+ consecutive sentences beginning with the same word
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) >= 3:
        first_words = []
        for s in sentences:
            w = s.split()
            if w:
                first_words.append(re.sub(r"[^a-z]", "", w[0].lower()))

        i = 0
        while i < len(first_words):
            run = 1
            while (
                i + run < len(first_words)
                and first_words[i + run] == first_words[i]
                and first_words[i]
            ):
                run += 1
            if run >= 3:
                parallel_bonus += 0.05
                matched_patterns.append(
                    f"3+ consecutive sentences starting with '{first_words[i]}'"
                )
                i += run
            else:
                i += 1

    # Sentence pairs within 10% of each other in word count (uniform length pattern)
    if len(sentences) >= 2:
        lengths = [len(s.split()) for s in sentences]
        uniform_pairs = sum(
            1
            for j in range(len(lengths) - 1)
            if lengths[j] > 0
            and lengths[j + 1] > 0
            and min(lengths[j], lengths[j + 1]) / max(lengths[j], lengths[j + 1]) >= 0.90
        )
        if uniform_pairs >= 2:
            parallel_bonus += 0.05
            matched_patterns.append(
                f"uniform sentence length ({uniform_pairs} adjacent pairs within 10%)"
            )

    rule_score = round(min(1.0, base_score + parallel_bonus), 4)
    return rule_score, matched_patterns
