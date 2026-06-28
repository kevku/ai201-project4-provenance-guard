import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from pipeline.rule_analyzer import analyze


def run_test(label: str, text: str) -> None:
    word_count = len(text.split())
    print(f"\n{'=' * 65}")
    print(f"TEST: {label}  ({word_count} words)")
    print("=" * 65)
    try:
        score, patterns = analyze(text)
        print(f"Rule Score : {round(score, 4)}")
        print(f"Matched ({len(patterns)} total):")
        if patterns:
            for p in patterns:
                print(f"  - {p}")
        else:
            print("  (none)")
    except ValueError as e:
        print(f"Rejected   : {e}")


# Expected: rejected — under 40 words
SHORT_TEXT = (
    "This is a very short piece of text. It does not meet the minimum word "
    "count requirement for analysis."
)

# Expected: score 0.75–0.85, 8–9 filler phrase matches
FILLER_HEAVY = (
    "It is important to note that modern technology has changed the way we live. "
    "At the end of the day, it goes without saying that progress is inevitable. "
    "Needless to say, it is what it is. With that said, to put it simply, we must "
    "adapt. First and foremost, it is no secret that change is constant. Last but "
    "not least, as we can see, the future is uncertain."
)

# Expected: score 0.20–0.30, parallel structure matches only
PARALLEL_ONLY = (
    "It is not just about the technology, it is about the people. Whether we "
    "succeed or whether we fail depends on our choices. This is not about profit. "
    "It is about purpose. Not only does this affect individuals but also entire "
    "communities. We rise together. We fall together. We build together."
)

# Expected: score 0.20–0.30, em-dash matches only
EMDASH_ONLY = (
    "The results were clear — undeniable, even. Three factors emerged — timing, "
    "context, and execution. The team disagreed — not on the goal — but on the "
    "method. Every decision carried weight — financial, ethical, personal. The "
    "conclusion was simple — act now or lose the opportunity entirely. No one "
    "argued — the data spoke for itself."
)

# Expected: score 0.85–0.95, all three signals firing
ALL_SIGNALS = (
    "It is important to note that the results were clear — undeniable, even. "
    "At the end of the day, it is not just about the data, it is about the insight. "
    "First and foremost, whether we act or whether we wait determines the outcome — "
    "entirely. Needless to say, this is not about speed. It is about precision. "
    "With that said, last but not least, the conclusion is simple — we must adapt."
)

# Expected: score 0.05–0.15, one em-dash at most
HUMAN_TEXT = (
    "My grandmother taught me to make bread on Sunday mornings. She never measured "
    "anything — a handful of this, a pinch of that. I burned the first three loaves "
    "I tried on my own. The fourth one came out dense but edible, and I ate it "
    "standing over the sink feeling unreasonably proud of myself."
)


run_test("Too Short — under 40 words (expect rejection)", SHORT_TEXT)
run_test("Filler Heavy — filler phrases only (expect 0.75–0.85)", FILLER_HEAVY)
run_test("Parallel Only — no filler or em-dash (expect 0.20–0.30)", PARALLEL_ONLY)
run_test("Em-Dash Only — no filler or parallel (expect 0.20–0.30)", EMDASH_ONLY)
run_test("All Signals — filler + parallel + em-dash (expect 0.85–0.95)", ALL_SIGNALS)
run_test("Human Text — personal anecdote (expect 0.05–0.15)", HUMAN_TEXT)
