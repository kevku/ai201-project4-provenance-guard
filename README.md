# Provenance Guard

An AI content detection API that analyzes text for signs of AI generation using two independent signals — a deterministic rule-based analyzer and a Groq LLM semantic analyzer — then combines them into a single transparency label. Creators can appeal decisions they believe are incorrect.

---

## Architecture Overview

Every submission to `POST /submit` travels through the following stages in order:

1. **API layer (`app.py`)** — validates that `text` and `creator_id` are present, then fans out to both analyzers.

2. **Rule analyzer (`pipeline/rule_analyzer.py`)** — scans the raw text for em-dash frequency, filler phrase density, and parallel structure patterns. Returns a `rule_score` (0.0–1.0) and a list of every matched phrase or pattern. Rejects text under 40 words before scoring.

3. **Groq analyzer (`pipeline/groq_analyzer.py`)** — sends the text to `llama-3.3-70b-versatile` via the Groq API with a structured prompt asking it to score redundancy, empty praise, and undeveloped ideas on anchored 0.0–1.0 scales. Returns a `groq_score` (the mean of the three dimensions) and a one-sentence reasoning string.

4. **Confidence scorer (`pipeline/confidence.py`)** — combines the two scores with a weighted formula, applies a disagreement override when the two signals diverge sharply, and maps the result to one of three confidence bands.

5. **Label generator (`pipeline/confidence.py`, `_LABELS` dict)** — selects the exact transparency label string for the confidence band.

6. **SQLite (`db/database.py`)** — stores the full record: both raw scores, matched patterns, Groq reasoning, final score, confidence band, label, and appeal status.

7. **Response** — the API returns the content ID, label, final score, confidence band, and all signal detail to the caller.

---

## Detection Signals

### Signal 1: Rule-Based Surface Patterns (Python, 40% weight)

**What it measures:** Three categories of surface-level patterns:
- *Em-dash frequency* — counts `—` characters relative to word count, scaled to 0.0–1.0.
- *Filler phrase density* — matches 24 known AI-associated phrases (e.g. "at the end of the day", "it goes without saying", "first and foremost") against the normalized text, then divides by word count per 100 words.
- *Parallel structure* — four regex patterns (e.g. "not only...but also", "whether...or"), runs of 3+ consecutive sentences starting with the same word, and adjacent sentence-pairs within 10% of each other in word count. Each hit adds 0.05 to the score.

**Why chosen:** Fully deterministic, runs in milliseconds, requires no external API, and is completely auditable — every matched phrase is logged in `matched_patterns`.

**What it misses:** Formal human writing (academic prose, legal documents) uses many of the same transition phrases. The analyzer is context-blind: it cannot tell whether "on the other hand" is ironic or structural. A literature review written by a human may score surprisingly high.

**Output:** `rule_score: float` (0.0–1.0), `matched_patterns: list[str]`

---

### Signal 2: Semantic Context Analysis (Groq LLM, 60% weight)

**What it measures:** Three meaning-level dimensions scored independently by the LLM:
- *Redundancy* — whether the same point is restated in different words with nothing new added (1.0 = same point restated 3+ times, nothing new).
- *Empty praise* — sweeping or vague claims with no supporting specifics (1.0 = "groundbreaking", "will reshape the landscape" throughout, zero evidence).
- *Undeveloped ideas* — claims raised and immediately abandoned without follow-through (1.0 = consistently dropped without explanation or illustration).

The `groq_score` is the mean of all three: `(redundancy + empty_praise + undeveloped_ideas) / 3`.

**Why chosen:** Captures meaning-level hollowness that regex cannot detect. A text can avoid every filler phrase on the list and still score 0.9 if it says nothing concrete. The LLM reads for substance, not surface.

**What it misses:** High-quality AI writing with genuine specificity and developed arguments will score low, same as strong human writing — the signal targets *hollow* AI output, not AI output in general. The score is also non-deterministic: the same text may return slightly different scores across two calls.

**Output:** `groq_score: float` (0.0–1.0), `reasoning: str` (one sentence)

---

## Confidence Scoring

### Combination formula

```
final_score = (rule_score × 0.40) + (groq_score × 0.60)
```

The Groq signal carries more weight because it evaluates meaning rather than surface patterns, making it harder to game and more robust to stylistic variation.

### Disagreement override

```
if abs(rule_score - groq_score) > 0.40:
    confidence_band = "uncertain"
    signals_agree = False
```

When the two signals disagree by more than 0.40, the system forces `uncertain` regardless of the weighted score. This prevents a single strong signal from dominating when the other signal contradicts it. For example, formal academic prose may produce a high rule score but a low Groq score — the override correctly surfaces that ambiguity instead of calling it AI-generated.

### Asymmetric thresholds

```
final_score < 0.35  → high_confidence_human
0.35 ≤ final_score < 0.65  → uncertain
final_score ≥ 0.65  → high_confidence_ai
```

The thresholds are deliberately asymmetric. Labeling human work as AI-generated is a more serious error than failing to catch AI-generated work — a false accusation can damage a creator's reputation, while a missed detection is merely a gap in coverage. As a result, the human band ends at 0.35 and the AI band only begins at 0.65, leaving a wide uncertain middle. The system requires stronger evidence to accuse than to clear.

### Example 1 — High confidence AI

**Input text:**
> It is important to note that modern technology has changed the way we live. At the end of the day, it goes without saying that progress is inevitable. Needless to say, it is what it is. With that said, to put it simply, we must adapt. First and foremost, it is no secret that change is constant. Last but not least, as we can see, the future is uncertain.

| Field | Value |
|---|---|
| `rule_score` | 1.0 |
| `groq_score` | 0.8333 |
| `final_score` | 0.9 |
| `confidence_band` | `high_confidence_ai` |
| `signals_agree` | `true` |

**matched_patterns (9):**
- `it goes without saying`
- `at the end of the day`
- `needless to say`
- `as we can see`
- `with that said`
- `to put it simply`
- `last but not least`
- `first and foremost`
- `uniform sentence length (3 adjacent pairs within 10%)`

**groq_reasoning:** "The text is dominated by repetitive, vague statements with no concrete evidence or development."

---

### Example 2 — High confidence human

**Input text:**
> ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was thin and kind of sweet in a way that did not taste intentional. noodles were fine but nothing special. i have had better from the instant pack honestly. the space was cute though and the staff were nice but i would not go back just for the food.

| Field | Value |
|---|---|
| `rule_score` | 0.0 |
| `groq_score` | 0.0 |
| `final_score` | 0.0 |
| `confidence_band` | `high_confidence_human` |
| `signals_agree` | `true` |

**matched_patterns:** `[]`

**groq_reasoning:** "the text provides specific criticisms and comparisons of the ramen place."

---

## Transparency Labels

The label text returned in every API response and stored in the database.

### ⚠ Likely AI-Generated (`high_confidence_ai`)

```
⚠ Likely AI-Generated
Our automated analysis found strong signals suggesting this content was produced with
AI assistance. This label is based on pattern detection — not a guarantee. If you are
the creator and believe this is wrong, you can submit an appeal below.
```

### ✓ Likely Human-Written (`high_confidence_human`)

```
✓ Likely Human-Written
Our automated analysis found no strong signals of AI generation in this content.
This reflects our best assessment, not a certainty.
```

### ◐ Origin Unclear (`uncertain`)

```
◐ Origin Unclear
Our system could not determine with confidence whether this content was written by
a human or generated with AI assistance. Mixed or inconclusive signals produced this
result — not evidence of wrongdoing. If you are the creator and believe this label
misrepresents your work, you can submit an appeal below.
```

---

## Rate Limiting

Limits are applied per IP address using Flask-Limiter with in-memory storage.

| Endpoint | Limit |
|---|---|
| `POST /submit` | 5 per minute, 20 per day |
| `POST /appeal` | 3 per day |
| `GET /log` | 30 per minute |
| `GET /appeals` | 30 per minute |

**Reasoning:** The Groq free tier allows approximately 1,000 requests per day. Each `POST /submit` consumes one Groq API call. The 20-per-day IP limit leaves budget for many concurrent users while preventing any single IP from exhausting quota. The 5-per-minute limit allows a creator to iterate on drafts quickly without burning through the daily limit in a single burst.

The `POST /appeal` limit is set low (3 per day) because appeals are human-driven decisions, not automated queries — a single creator should rarely need more than one or two per session.

**Rate limit test output (`POST /submit`, 7 consecutive requests):**

```
Request 1: 200
Request 2: 200
Request 3: 200
Request 4: 200
Request 5: 200
Request 6: 429
Request 7: 429
```

Exceeded requests return JSON (not Flask-Limiter's default HTML):
```json
{"error": "Rate limit exceeded. Please try again later."}
```

---

## Audit Log Sample

Retrieved via `GET /log`. Three representative entries showing different outcomes:

```json
{
    "entries": [
        {
            "appeal_status": "reviewed",
            "confidence_band": "high_confidence_ai",
            "content_id": "aa0a2edf-3118-4787-889a-3a4b31260b20",
            "creator_id": "ratelimit-test",
            "final_score": 0.88,
            "groq_reasoning": "The text consists of generic statements and phrases that convey no specific information or ideas.",
            "groq_score": 0.8,
            "ip": "127.0.0.1",
            "label_text": "⚠ Likely AI-Generated\nOur automated analysis found strong signals suggesting this content was produced with AI assistance. This label is based on pattern detection — not a guarantee. If you are the creator and believe this is wrong, you can submit an appeal below.",
            "matched_patterns": [
                "it goes without saying",
                "at the end of the day",
                "needless to say",
                "uniform sentence length (2 adjacent pairs within 10%)"
            ],
            "rule_score": 1.0,
            "text": "It is important to note that modern technology has changed the way we live. At the end of the day, it goes without saying that progress is inevitable. Needless to say, we must adapt and move forward with purpose and clarity.",
            "timestamp": "2026-06-28T10:52:03.185514+00:00",
            "word_count": 41
        },
        {
            "appeal_status": "reviewed",
            "confidence_band": "uncertain",
            "content_id": "1c1164ba-9790-4ab6-8949-c6f81192d2cc",
            "creator_id": "ratelimit-test",
            "final_score": 0.7,
            "groq_reasoning": "The text contains phrases that convey a sense of inevitability and importance, but lacks concrete examples or supporting evidence.",
            "groq_score": 0.5,
            "ip": "127.0.0.1",
            "label_text": "◐ Origin Unclear\nOur system could not determine with confidence whether this content was written by a human or generated with AI assistance. Mixed or inconclusive signals produced this result — not evidence of wrongdoing. If you are the creator and believe this label misrepresents your work, you can submit an appeal below.",
            "matched_patterns": [
                "it goes without saying",
                "at the end of the day",
                "needless to say",
                "uniform sentence length (2 adjacent pairs within 10%)"
            ],
            "rule_score": 1.0,
            "text": "It is important to note that modern technology has changed the way we live. At the end of the day, it goes without saying that progress is inevitable. Needless to say, we must adapt and move forward with purpose and clarity.",
            "timestamp": "2026-06-28T10:52:02.263853+00:00",
            "word_count": 41
        },
        {
            "appeal_status": "under_review",
            "confidence_band": "high_confidence_ai",
            "content_id": "63705194-e93b-4783-98c5-0403c4367b3e",
            "creator_id": "test-user-1",
            "final_score": 0.9,
            "groq_reasoning": "The text is filled with redundant, vague, and undeveloped statements.",
            "groq_score": 0.8333,
            "ip": "127.0.0.1",
            "label_text": "⚠ Likely AI-Generated\nOur automated analysis found strong signals suggesting this content was produced with AI assistance. This label is based on pattern detection — not a guarantee. If you are the creator and believe this is wrong, you can submit an appeal below.",
            "matched_patterns": [
                "it goes without saying",
                "at the end of the day",
                "needless to say",
                "as we can see",
                "with that said",
                "to put it simply",
                "last but not least",
                "first and foremost",
                "uniform sentence length (3 adjacent pairs within 10%)"
            ],
            "rule_score": 1.0,
            "text": "It is important to note that modern technology has changed the way we live. At the end of the day, it goes without saying that progress is inevitable. Needless to say, it is what it is. With that said, to put it simply, we must adapt. First and foremost, it is no secret that change is constant. Last but not least, as we can see, the future is uncertain.",
            "timestamp": "2026-06-28T10:45:06.625153+00:00",
            "word_count": 69
        }
    ]
}
```

---

## Known Limitations

**1. Academic and formal human writing triggers false positives in rule_analyzer.**

Parallel structures and rhetorical transitions are features of good scholarly writing, not just AI output. Phrases like "on the other hand", "first and foremost", and "in conclusion" appear throughout literature reviews, policy briefs, and persuasive essays written by humans. A high-scoring academic paper may land in `uncertain` even when the Groq signal correctly identifies subject-matter expertise — but the disagreement override will usually surface this ambiguity rather than calling it AI-generated.

**2. Short text near the 40-word minimum produces unreliable density scores.**

The filler phrase score is computed as `(filler_count / word_count) * 100`. At exactly 40 words, a single filler phrase produces a density rate of 2.5 per 100 words — the same rate a 200-word text would require five filler phrases to reach. The minimum word count requirement exists to mitigate this, but the boundary is still a noisy region where a single phrase choice has outsized influence on the final score.

**3. Non-English text is not detected or rejected.**

Planning.md specified that `langdetect` would be used to reject non-English submissions before the pipeline runs. That check was never implemented. The system processes non-English text and produces results that are technically valid but meaningless.

Two failure modes occur depending on how the text is submitted. Chinese text written naturally (no spaces between characters) is rejected immediately with a 400 "too short" error — not because it's non-English, but because `text.split()` counts whitespace-delimited tokens, and Chinese has almost none. The submission never reaches the pipeline. The rejection message incorrectly tells the creator to "submit at least 40 words," which is not the actual problem.

If the same Chinese text is submitted with spaces inserted between characters to clear the word count floor, the pipeline runs and produces a misleading result. Tested with a 68-token Chinese submission about technology and AI:

```json
{
    "attribution": "uncertain",
    "confidence": 0.3,
    "signals": {
        "rule_score": 0.0,
        "groq_score": 0.5,
        "matched_patterns": [],
        "groq_reasoning": "The text discusses the impact of modern technology and AI on society, but lacks specific details and examples to support its claims.",
        "signals_agree": false
    }
}
```

`rule_score` is 0.0 because the filler phrase list is entirely English — no patterns fire. Groq is multilingual and scores the content at 0.5 across all three dimensions (a default middling assessment when it has no strong signal). The gap between 0.0 and 0.5 exceeds the 0.40 disagreement threshold, so the override fires and returns `uncertain`. The label is not genuinely uncertain — the signals disagreed because one of them is the wrong tool for the input, not because the content is ambiguous.

---

## Spec Reflection

**One way the spec helped:**

The spec explicitly warned that labeling human work as AI is worse than a false negative. That framing directly shaped the asymmetric threshold design — the human band ends at 0.35 while the AI band only starts at 0.65. Without that framing, the natural default would have been symmetric thresholds around 0.5, which would have produced more false accusations.

**One way implementation diverged:**

The spec suggested in-memory storage. SQLite was chosen instead because in-memory storage resets on every server restart, making it impossible to demonstrate a persistent audit log across sessions or test the appeals workflow realistically. Appeals only make sense if the original submission record survives between requests; a restarting in-memory store would lose that record.

---

## AI Usage

**1. Brainstorming and Process**

Using Claude on the free version helped me minimize token usage and helped me create a planning.md which I could feed to a better model on VSCode. Extensive planning helped make the process of building the application easier as I was able to step-by-step review it's changes to a function and have it test certain cases mentioned on my planning. Since it helped me plan, there was one casce where I forgot that I wanted to add a case where it should accomodate foreign language or have a proper response rather than just accepting that it's not AI.

**2. Generating the confidence scorer.**

Claude produced a version where `final_score` was computed before the disagreement check, which is correct. However the initial version applied a symmetric disagreement override: if either signal was much higher than the other, both directions were forced to `uncertain`. This was correct but revealed an interesting design question during testing: the parallel structure text (`rule_score=0.25`, `groq_score=0.83`) was landing in `uncertain` via the override, which was actually the intended behavior. Discussion about whether Python or Groq should be trusted when they disagree led to the decision to keep the override symmetric — neither signal dominates when they conflict — rather than giving Groq a tiebreak advantage.

## Video
[Walkthrough](https://www.loom.com/share/ad3fc360f7484fef9c43bf658c9cc39b)

---

## Setup

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Configure environment:**
```bash
touch .env
# Add your Groq API key to .env:
# GROQ_API_KEY=your_key_here
```

**Run the server:**
```bash
python app.py
```

The server starts on port 5001 to avoid conflict with macOS AirPlay Receiver, which occupies port 5000 by default.

**Endpoints:**

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/submit` | Analyze text and return a transparency label |
| `POST` | `/appeal` | Submit an appeal for a prior decision |
| `GET` | `/log` | Retrieve the 20 most recent submissions |
| `GET` | `/appeals` | Retrieve all appeals currently under review |


