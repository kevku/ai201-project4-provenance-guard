import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from pipeline.confidence import score

CASES = [
    ("Both high — expect high_confidence_ai",      0.80, 0.85),
    ("Both low — expect high_confidence_human",    0.20, 0.15),
    ("Both middle — expect uncertain",             0.50, 0.55),
    ("Groq high, rule low — expect uncertain + disagree", 0.25, 0.83),
    ("Rule high, Groq low — expect uncertain + disagree", 0.75, 0.20),
]

for label, rule_score, groq_score in CASES:
    result = score(rule_score, groq_score)
    print(f"\n{'=' * 60}")
    print(f"CASE: {label}")
    print(f"  rule_score={rule_score}  groq_score={groq_score}")
    print(f"  final_score    : {result['final_score']}")
    print(f"  confidence_band: {result['confidence_band']}")
    print(f"  signals_agree  : {result['signals_agree']}")
