_LABELS = {
    "high_confidence_human": (
        "✓ Likely Human-Written\n"
        "Our automated analysis found no strong signals of AI generation in this content. "
        "This reflects our best assessment, not a certainty."
    ),
    "uncertain": (
        "◐ Origin Unclear\n"
        "Our system could not determine with confidence whether this content was written by "
        "a human or generated with AI assistance. Mixed or inconclusive signals produced this "
        "result — not evidence of wrongdoing. If you are the creator and believe this label "
        "misrepresents your work, you can submit an appeal below."
    ),
    "high_confidence_ai": (
        "⚠ Likely AI-Generated\n"
        "Our automated analysis found strong signals suggesting this content was produced with "
        "AI assistance. This label is based on pattern detection — not a guarantee. If you are "
        "the creator and believe this is wrong, you can submit an appeal below."
    ),
}


def score(rule_score: float, groq_score: float) -> dict:
    """
    Combine rule and Groq signals into a final confidence result.

    Returns:
        {
            "final_score": float,
            "confidence_band": str,
            "signals_agree": bool,
            "label_text": str,
        }
    """
    final_score = round((rule_score * 0.40) + (groq_score * 0.60), 4)

    if abs(rule_score - groq_score) > 0.40:
        confidence_band = "uncertain"
        signals_agree = False
    else:
        signals_agree = True
        if final_score < 0.35:
            confidence_band = "high_confidence_human"
        elif final_score < 0.65:
            confidence_band = "uncertain"
        else:
            confidence_band = "high_confidence_ai"

    return {
        "final_score": final_score,
        "confidence_band": confidence_band,
        "signals_agree": signals_agree,
        "label_text": _LABELS[confidence_band],
    }
