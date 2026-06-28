import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

import groq as _groq_sdk
from pipeline import groq_analyzer


def run_test(label: str, text: str) -> None:
    word_count = len(text.split())
    print(f"\n{'=' * 65}")
    print(f"TEST: {label}  ({word_count} words)")
    print("=" * 65)
    try:
        result = groq_analyzer.analyze(text)
        print(f"Groq Score       : {result['groq_score']}")
        print(f"  redundancy     : {result['redundancy']}")
        print(f"  empty_praise   : {result['empty_praise']}")
        print(f"  undeveloped    : {result['undeveloped_ideas']}")
        print(f"Reasoning        : {result['reasoning']}")
    except RuntimeError as e:
        print(f"RuntimeError     : {e}")


# Expected: groq_score above 0.70 — vague superlatives, no concrete detail
AI_TEXT = (
    "Artificial intelligence represents a transformative paradigm shift in "
    "modern society. It is important to note that while the benefits of AI "
    "are numerous, it is equally essential to consider the ethical implications. "
    "Furthermore, stakeholders across various sectors must collaborate to ensure "
    "responsible deployment. This groundbreaking technology will reshape the "
    "landscape of human endeavor in ways that are truly remarkable and "
    "unprecedented in scope."
)

# Expected: groq_score below 0.30 — specific detail, personal narrative, concrete memory
HUMAN_TEXT = (
    "My grandmother taught me to make bread on Sunday mornings. She never "
    "measured anything — a handful of this, a pinch of that. I burned the "
    "first three loaves I tried on my own. The fourth one came out dense but "
    "edible, and I ate it standing over the sink feeling unreasonably proud "
    "of myself."
)

# Expected: groq_score 0.30–0.55 — rhetorical style but real meaning present
PARALLEL_TEXT = (
    "It is not just about the technology, it is about the people. Whether "
    "we succeed or whether we fail depends on our choices. This is not about "
    "profit. It is about purpose. Not only does this affect individuals but "
    "also entire communities. We rise together. We fall together. We build "
    "together."
)


run_test("Obvious AI Text (expect 0.70+)", AI_TEXT)
run_test("Human Text — grandmother story (expect 0.00–0.30)", HUMAN_TEXT)
run_test("Parallel Structure Only (expect 0.30–0.55)", PARALLEL_TEXT)

# Simulate Groq unavailable by swapping in an invalid API key
print(f"\n{'=' * 65}")
print("TEST: Groq Unavailable — invalid API key (expect RuntimeError)")
print("=" * 65)
original_client = groq_analyzer._client
groq_analyzer._client = _groq_sdk.Groq(api_key="invalid_key_gsk_test", timeout=10.0)
try:
    groq_analyzer.analyze(AI_TEXT)
    print("ERROR: Should have raised RuntimeError")
except RuntimeError as e:
    print(f"Correctly raised RuntimeError: {e}")
finally:
    groq_analyzer._client = original_client
