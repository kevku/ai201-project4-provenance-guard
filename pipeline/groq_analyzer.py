import json
import os

import groq
from dotenv import load_dotenv

load_dotenv()

_UNAVAILABLE = "Analysis service temporarily unavailable. Please try again later."

_PROMPT = """\
Analyze this text for signs of AI generation. Score each dimension 0.0–1.0
using these anchored definitions:

redundancy:
  0.0 = every paragraph introduces genuinely new information
  0.5 = some restatement but new ideas still appear
  1.0 = the same point is restated 3+ times in different words, nothing new added

empty_praise:
  0.0 = all claims are backed by specific detail or evidence
  0.5 = some unsupported claims but concrete content also present
  1.0 = sweeping or vague claims throughout ("groundbreaking", "will reshape \
the landscape", "truly remarkable") with no specifics, or language \
that sounds meaningful but says nothing concrete

undeveloped_ideas:
  0.0 = every claim is explained, evidenced, or illustrated
  0.5 = some points are developed, others dropped
  1.0 = claims are consistently raised and immediately abandoned \
with no follow-through

Return ONLY valid JSON with no explanation outside it:
{{
  "redundancy": 0.0,
  "empty_praise": 0.0,
  "undeveloped_ideas": 0.0,
  "reasoning": "one sentence explanation of the dominant signal"
}}

Text to analyze:
{text}"""

_client = groq.Groq(api_key=os.environ.get("GROQ_API_KEY"), timeout=10.0)


def _extract_json(raw: str) -> str:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object in response")
    return raw[start : end + 1]


def analyze(text: str) -> dict:
    """
    Call Groq to score text for AI-generation signals.

    Returns:
        {
            "groq_score": float,
            "redundancy": float,
            "empty_praise": float,
            "undeveloped_ideas": float,
            "reasoning": str,
        }

    Raises:
        RuntimeError: if Groq is unavailable, times out, or returns malformed JSON.
    """
    try:
        response = _client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": _PROMPT.format(text=text)}],
        )
        raw = response.choices[0].message.content
    except Exception as exc:
        raise RuntimeError(_UNAVAILABLE) from exc

    try:
        data = json.loads(_extract_json(raw))
        redundancy = float(data["redundancy"])
        empty_praise = float(data["empty_praise"])
        undeveloped_ideas = float(data["undeveloped_ideas"])
        reasoning = str(data["reasoning"])
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(_UNAVAILABLE) from exc

    groq_score = round((redundancy + empty_praise + undeveloped_ideas) / 3, 4)
    return {
        "groq_score": groq_score,
        "redundancy": redundancy,
        "empty_praise": empty_praise,
        "undeveloped_ideas": undeveloped_ideas,
        "reasoning": reasoning,
    }
