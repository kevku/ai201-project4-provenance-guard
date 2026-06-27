# Provenance Guard — Planning Document

---

## Detection Signals

### Signal 1: Rule-Based Surface Patterns (Python, 40%)

**What it measures:**
Three surface-level properties of the text that correlate with AI generation:
- **Em-dash frequency** — count of `—` characters normalized per 100 words
- **Filler phrase density** — count of hollow, meaning-free phrases normalized per 100 words
- **Parallel structure frequency** — count of syntactic repetition patterns detected via regex, normalized per sentence count

**Why these differ between human and AI writing:**
LLMs are trained on human feedback that rewards clear, well-structured prose. This produces text that unconsciously mirrors rhetorical templates: balanced sentence pairs, transition phrases that signal structure without adding meaning ("It's important to note," "At the end of the day"), and punctuation like em-dash that appears frequently in formal training data. Human writers are messier — they vary rhythm unpredictably and don't consistently reach for the same transitional scaffolding.

**Output format:**
A float between 0.0 and 1.0. Computed as:
```
rule_score = min(1.0, (emdash_score * 0.25) + (filler_density * 0.75))
```
Parallel structure hits add a small bonus on top, capped at 1.0.

The signal also returns a list of every matched phrase and pattern — for example `["it's important to note", "—", "not only...but also"]`. This list is stored in SQLite and shown to a human reviewer so they can see exactly what the rule analyzer flagged, not just a number.

**Short text handling:**
If word count is under 150 words, rule analysis is skipped entirely and the system returns a 400 response:
```
"This content is too short for reliable analysis. 
Submit at least 150 words for a confident result."
```
Below 150 words, density math produces meaningless scores — one filler phrase in a short paragraph becomes an inflated density rate that carries no real signal. Real detectors (GPTZero and others) apply the same minimum length floor.

**Filler phrase list:**
```
"it's important to note"
"it goes without saying"
"at the end of the day"
"in today's world"
"this raises important questions"
"it's worth noting"
"in conclusion"
"needless to say"
"as we can see"
"at its core"
"the fact of the matter"
"when all is said and done"
"it's no secret that"
"more often than not"
"in the grand scheme of things"
"it's fair to say"
"building on this"
"with that said"
"to put it simply"
"last but not least"
"first and foremost"
"on the other hand"
"it's crucial to understand"
"it's no surprise that"
```

**Parallel structure regex patterns:**
```
"it's not just .+, it's"
"not only .+ but also"
"this isn't about .+\. it's about"
"whether .+ or .+"
3+ consecutive sentences beginning with the same word
sentence pairs within 10% of each other in word count
```

**Blind spots:**
- Academic and formal human writing naturally uses parallel structures and transition phrases
- Marketing copy and corporate communications are full of filler phrases written by humans
- Em-dash is a legitimate stylistic choice for many human writers
- Text under 150 words is rejected before scoring runs

---

### Signal 2: Semantic Context Analysis (Groq LLM, 60%)

**What it measures:**
Three semantic properties that require understanding meaning across sentences — things regex cannot detect:
- **Redundancy** — does the text restate the same ideas multiple times in different words without adding new information?
- **Empty praise** — does the text make sweeping claims ("groundbreaking," "revolutionary," "transformative") without concrete evidence or specifics?
- **Undeveloped ideas** — are claims made and immediately abandoned, with the text moving on before actually explaining or evidencing the point?

**Why these differ between human and AI writing:**
LLMs optimize for plausible-sounding continuation. When a model lacks genuine information to add, it restates what was already said or reaches for evaluative language rather than substantive content. Human writers who are genuinely engaged with a topic develop their ideas — they give examples, push back on their own claims, get specific. AI writing tends to stay at the level of assertion without descending into evidence.

**Output format:**
Groq returns a JSON object with three sub-scores (each 0.0–1.0), anchored definitions guide what each value means, and a one-sentence reasoning string. These sub-scores are averaged into a single `groq_score` float between 0.0 and 1.0. The reasoning string is stored in SQLite and shown to a human reviewer alongside the score.

**Groq prompt:**
```
Analyze this text for signs of AI generation. Score each dimension 0.0–1.0
using these anchored definitions:

redundancy:
  0.0 = every paragraph introduces genuinely new information
  0.5 = some restatement but new ideas still appear
  1.0 = the same point is restated 3+ times in different words, nothing new added

empty_praise:
  0.0 = all claims are backed by specific detail or evidence
  0.5 = some unsupported claims but concrete content also present
  1.0 = sweeping or vague claims throughout ("groundbreaking", "will reshape the landscape", "truly remarkable") with no specifics, or language that sounds meaningful but says nothing concrete

undeveloped_ideas:
  0.0 = every claim is explained, evidenced, or illustrated
  0.5 = some points are developed, others dropped
  1.0 = claims are consistently raised and immediately abandoned with no follow-through

Return ONLY valid JSON with no explanation outside it:
{
  "redundancy": 0.0,
  "empty_praise": 0.0,
  "undeveloped_ideas": 0.0,
  "reasoning": "one sentence explanation of the dominant signal"
}
```

**Groq unavailability:**
If Groq is unavailable (timeout after 10 seconds, network error, or malformed response), the submission is rejected and the user is told to try again later:
```
"Our analysis service is temporarily unavailable. Please try again in a few minutes."
```
Groq is 60% of the confidence score. Returning a result without it would produce a misleading verdict, so the system does not issue a degraded response — it waits until both signals can run.

**Blind spots:**
- High-quality AI writing given rich context may develop ideas convincingly and score low
- Genuinely hollow human writing (bad blog posts, low-effort content) may score high
- Groq's scoring is not fully deterministic — the same text submitted twice may return slightly different scores
- Groq is itself an LLM and may carry its own biases about what "AI-like" prose looks like

---

### Combining Signals into a Confidence Score

**Step 1 — Disagreement check:**
Before computing any weighted average, check whether the two signals strongly disagree:
```
if abs(rule_score - groq_score) > 0.40:
    confidence_band = "uncertain"
```
This runs first. If it fires, the band is set to uncertain regardless of what the weighted average would have produced. The signals are telling different stories — the system does not force a verdict.

**Step 2 — Weighted average:**
```
final_score = (rule_score * 0.40) + (groq_score * 0.60)
```
Groq receives more weight because semantic analysis is a stronger signal than surface patterns. A human can accidentally use filler phrases; it is harder to accidentally write like an LLM at the level of idea development.

**Step 3 — Band mapping:**
```
final_score < 0.35          →  band = "high_confidence_human"
0.35 <= final_score < 0.65  →  band = "uncertain"
final_score >= 0.65         →  band = "high_confidence_ai"
```
The human threshold (0.35) is intentionally lower than the AI threshold (0.65). The system requires more evidence to accuse than to clear. A false positive on a writing platform — labeling a human writer's work as AI-generated — is a reputational harm that a missed detection is not.

---

## Uncertainty Representation

**What does 0.6 mean?**
A score of 0.6 means the weighted average of both signals landed at 0.6 — inside the uncertain band (0.35–0.65), leaning toward AI but not enough to say so confidently. The label shown to the reader reflects ambiguity, not accusation. The raw score is preserved in SQLite and returned in the API response for transparency.

**What does 0.95 mean vs 0.65?**
Both produce the "high_confidence_ai" label, but 0.95 means both signals agreed strongly and the weighted average came out high. 0.65 is the minimum threshold — it may mean one signal was high and the other moderate. The confidence score is always included in the API response so the platform can display it alongside the label if they want finer granularity.

**Thresholds:**
```
< 0.35     →  high_confidence_human
0.35–0.65  →  uncertain
> 0.65     →  high_confidence_ai
```

**How scores are tested for meaningfulness:**
Before finalizing thresholds, the pipeline will be tested against a small set of known inputs:
- Clearly AI text (LLM output with no editing) — expected score above 0.65
- Clearly human text (personal essays, conversational writing) — expected score below 0.35
- Edge cases (academic writing, heavily edited AI drafts) — expected score in uncertain band

If known-human samples are consistently scoring above 0.5, signal weights or thresholds need adjustment.

---

## Transparency Label Variants

These are the exact strings the platform displays to a reader.

### High-Confidence AI
> **⚠ Likely AI-Generated**
> Our automated analysis found strong signals suggesting this content was produced with AI assistance. This label is based on pattern detection — not a guarantee. If you are the creator and believe this is wrong, you can submit an appeal below.

---

### High-Confidence Human
> **✓ Likely Human-Written**
> Our automated analysis found no strong signals of AI generation in this content. This reflects our best assessment, not a certainty.

---

### Uncertain
> **◐ Origin Unclear**
> Our system could not determine with confidence whether this content was written by a human or generated with AI assistance. Mixed or inconclusive signals produced this result — not evidence of wrongdoing. If you are the creator and believe this label misrepresents your work, you can submit an appeal below.

---

## Appeals Workflow

**Who can submit an appeal?**
Anyone who has the `content_id` for a piece of content. The `content_id` acts as the access token — whoever submitted the content received it in the original response. No authentication system is required for this project.

**Rate limiting appeals:**
To prevent abuse, appeals are limited to **1 appeal per `content_id`** — you cannot keep appealing the same decision. IP-based limiting of **3 appeals per IP per day** across all content prevents one person from flooding the appeal queue with different submissions.

**What does the creator provide?**
```json
{
  "content_id": "uuid",
  "creator_id": "string (their IP or a self-identified name)",
  "reasoning": "string — their explanation in plain language"
}
```
The `reasoning` field is required. An appeal with no reasoning is rejected with a 400 error.

**What happens when an appeal is received?**
1. System looks up `content_id` in SQLite. Returns 404 if not found.
2. System checks whether an appeal already exists for this `content_id`. Returns 400 if one does.
3. Content record's `appeal_status` is updated from `"reviewed"` to `"under_review"`.
4. A new row is inserted into the appeals table containing: `appeal_id`, `content_id`, `creator_id`, `reasoning`, `appeal_timestamp`.
5. API returns confirmation with `appeal_id` and new status.

No automated re-classification runs. The appeal is a flag for human review only.

**What does a human reviewer see?**
`GET /appeals` returns all records with `appeal_status = "under_review"`, each containing the appeal details joined with the original decision:

```json
{
  "appeal_id": "uuid",
  "content_id": "uuid",
  "creator_id": "string",
  "reasoning": "string",
  "appeal_timestamp": "ISO 8601",
  "original_decision": {
    "text": "the submitted content",
    "rule_score": 0.0,
    "matched_patterns": ["pattern 1", "pattern 2"],
    "groq_score": 0.0,
    "groq_reasoning": "string",
    "final_score": 0.0,
    "confidence_band": "string",
    "label_text": "exact string shown to user",
    "timestamp": "ISO 8601"
  }
}
```

The reviewer sees the creator's reasoning, the matched patterns that triggered the rule signal, and Groq's one-sentence reasoning — enough context to make a judgment without re-running the pipeline.

---

## Anticipated Edge Cases

### Edge Case 1: Academic or Formal Human Writing
A professor submits a literature review. They naturally use parallel structures ("not only X but also Y"), disciplined transitions ("it is worth noting," "building on this"), and balanced paragraph construction — all hallmarks of formal academic style that also appear heavily in AI writing. The rule-based signal scores this high. Groq may also score it moderately high because academic writing deliberately avoids personal voice and anecdote, which Groq associates with undeveloped or impersonal prose.

**Likely output:** High combined score, possibly crossing into "high_confidence_ai." This is a false positive.

**Why the system handles it this way:** The signals are genuinely ambiguous for this content type. The appeals workflow exists for this scenario — the professor submits an appeal explaining the context, which a human reviewer can act on.

---

### Edge Case 2: AI Writing Heavily Edited by a Human
A creator generates a first draft with an LLM, then rewrites it substantially — adding personal anecdotes, specific examples, and their own voice. Filler phrases get cleaned out. Parallel structures get broken up. Groq sees developed ideas and concrete detail and scores it low (0.25). The rule-based signal catches a few leftover structural patterns and scores it moderate (0.45). The gap between signals is 0.20 — not enough to trigger the disagreement override, but the weighted average lands around 0.33, just inside the human band.

**Likely output:** "high_confidence_human" or "uncertain" depending on exact scores. The content is genuinely hybrid — the label will not be fully accurate either way.

**Why the system handles it this way:** The system cannot resolve "partially AI" into a clean verdict. Uncertain is the most honest output. The appeals workflow exists if the creator feels even "uncertain" misrepresents their work.

---

### Edge Case 3: Text Too Short to Score (Under 150 Words)
A creator submits a product tagline, a haiku, a short poem, or a single paragraph. Density-based scoring breaks down at small sample sizes — one filler phrase in 30 words produces an inflated density rate that is not meaningful evidence. Groq also struggles with short text because there is not enough content to evaluate redundancy or idea development across sentences.

**Likely output:** The submission is rejected before the pipeline runs with a message explaining the minimum length requirement. This is consistent with how real AI detectors handle short text — GPTZero and similar tools apply the same floor.

**Why the system handles it this way:** Returning a confident verdict on 50 words would be worse than rejecting the request honestly. Short text is a known failure mode of density-based detection, and graceful rejection is better than a misleading score.

---

## SQLite Schema

### content table
```
content_id        TEXT  PRIMARY KEY    -- UUID4
ip                TEXT               -- submitter IP address
timestamp         TEXT               -- UTC datetime ISO 8601
word_count        INTEGER            -- total words in submitted text
text              TEXT               -- full submission text
rule_score        REAL               -- python signal score (0.0–1.0)
matched_patterns  TEXT               -- JSON list e.g. ["in conclusion", "—"]
groq_score        REAL               -- groq signal score (0.0–1.0)
groq_reasoning    TEXT               -- one-sentence explanation from Groq
final_score       REAL               -- weighted combined score (0.0–1.0)
confidence_band   TEXT               -- "high_confidence_human" | "uncertain" | "high_confidence_ai"
label_text        TEXT               -- exact string shown to the user
appeal_status     TEXT               -- "reviewed" | "under_review"
```

### appeals table
```
appeal_id         TEXT  PRIMARY KEY    -- UUID4
content_id        TEXT               -- foreign key → content.content_id
creator_id        TEXT               -- IP or self-identified name
reasoning         TEXT               -- creator's explanation
appeal_timestamp  TEXT               -- UTC datetime ISO 8601
```

---

## Rate Limiting

**Real Groq free tier limits (as of 2026):**
- 30 requests per minute
- 6,000 tokens per minute
- 1,000 requests per day

Every `POST /submit` = 1 Groq call. Working backwards from 1,000 calls/day with headroom for development and testing (~800 user-facing calls/day):

```
800 calls/day ÷ 24 hours = ~33/hour = roughly 1 every 2 minutes sustained
```

**Chosen limits:**

| Endpoint | Limit | Reasoning |
|---|---|---|
| `POST /submit` | 5 per minute per IP | Allows a creator to submit several drafts in a session without burning Groq quota |
| `POST /submit` | 20 per day per IP | Prevents one user from exhausting the shared daily Groq budget |
| `POST /appeal` | 1 per content_id | Cannot keep appealing the same decision |
| `POST /appeal` | 3 per day per IP | Prevents appeal queue flooding across different submissions |
| `GET /log` | 30 per minute per IP | Read-only, cheap, but still limited to prevent scraping |
| `GET /appeals` | 30 per minute per IP | Same reasoning as log endpoint |

**Text length cap:**
Incoming text is capped at **2,000 words (~2,500 tokens)**. A single long submission could consume nearly half the 6,000 TPM budget on its own when the Groq prompt template tokens are included. The cap is validated before the Groq call runs — oversized submissions are rejected with a 400 error explaining the limit.

---

## Architecture

```
SUBMISSION FLOW
===============

Creator
  │
  │  POST /submit { content, creator_id }
  ▼
┌──────────────────────┐
│   Flask API Layer    │── rate limit check ────► 429 if exceeded
│                      │── word count < 150 ───► 400 too short
│                      │── word count > 2000 ──► 400 too long
└──────────┬───────────┘
           │ raw text
           ▼
┌──────────────────────────────────────────────────────────────┐
│                    Detection Pipeline                         │
│                                                              │
│  ┌──────────────────────┐    ┌────────────────────────────┐  │
│  │  Rule-Based Analyzer │    │  Groq Semantic Analyzer    │  │
│  │  (Python, 40%)       │    │  (Groq API, 60%)           │  │
│  │                      │    │                            │  │
│  │  - em-dash count     │    │  - redundancy score        │  │
│  │  - filler density    │    │  - empty praise score      │  │
│  │  - parallel structs  │    │  - undeveloped ideas score │  │
│  │                      │    │  - reasoning string        │  │
│  │  returns:            │    │                            │  │
│  │  rule_score (0–1)    │    │  returns:                  │  │
│  │  matched_patterns[]  │    │  groq_score (0–1)          │  │
│  │                      │    │  groq_reasoning (string)   │  │
│  └──────────┬───────────┘    └──────────────┬─────────────┘  │
│             │                               │                 │
│             │  if Groq unavailable ─────────► 503 try later  │
│             │                               │                 │
│             └───────────────┬───────────────┘                 │
│                             │                                 │
│                    ┌────────▼─────────┐                       │
│                    │ Confidence       │                       │
│                    │ Scorer           │                       │
│                    │                  │                       │
│                    │ 1. disagree chk  │                       │
│                    │ 2. weighted avg  │                       │
│                    │ 3. band mapping  │                       │
│                    └────────┬─────────┘                       │
│                             │ final_score + band              │
└─────────────────────────────┼───────────────────────────────-┘
                              │
                     ┌────────▼─────────┐
                     │  Label Generator │
                     │                  │
                     │  band → exact    │
                     │  label string    │
                     └────────┬─────────┘
                              │ label_text
                     ┌────────▼─────────┐
                     │  SQLite Logger   │◄── writes full row to content table
                     └────────┬─────────┘
                              │
                     ┌────────▼─────────┐
                     │  API Response    │──► { content_id, attribution,
                     └──────────────────┘      final_score, confidence_band,
                                               label_text, rule_score,
                                               matched_patterns, groq_score,
                                               groq_reasoning }


APPEAL FLOW
===========

Creator
  │
  │  POST /appeal { content_id, creator_id, reasoning }
  ▼
┌──────────────────────┐
│   Flask API Layer    │── rate limit check ──────► 429 if exceeded
│                      │── lookup content_id ─────► 404 if not found
│                      │── appeal exists? ────────► 400 already appealed
│                      │── reasoning empty? ──────► 400 reasoning required
└──────────┬───────────┘
           │ validated appeal
           ▼
┌──────────────────────┐
│   Status Updater     │  content.appeal_status: "reviewed" → "under_review"
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   SQLite Logger      │  inserts row into appeals table linked by content_id
└──────────┬───────────┘
           │
┌──────────▼───────────┐
│   API Response       │──► { appeal_id, content_id, status: "under_review",
└──────────────────────┘      message: "Your appeal has been received..." }


REVIEWER FLOW
=============

Reviewer
  │
  │  GET /appeals
  ▼
┌──────────────────────┐
│   Flask API Layer    │── rate limit check
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   SQLite Query       │  SELECT appeals JOIN content WHERE appeal_status
│                      │  = "under_review"
└──────────┬───────────┘
           │
┌──────────▼───────────┐
│   API Response       │──► [ { appeal_id, reasoning, original_decision:
└──────────────────────┘        { text, matched_patterns, groq_reasoning,
                                  final_score, label_text } } ]
```

**Narrative:**
A submission enters the Flask API, passes rate limiting and length validation, then runs through two independent signals — a Python rule analyzer and a Groq semantic analyzer — whose scores are combined by the confidence scorer into a final band and label. The full decision record is written to SQLite before the response is returned. An appeal enters the same API layer, validates the content exists, checks no prior appeal exists, updates the content status to "under_review," and inserts a new row into the appeals table linked to the original decision — no re-classification runs. A reviewer calls GET /appeals to see all pending appeals joined with their original decision context.

---

## AI Tool Plan

### M3 — Submission Endpoint + First Signal

**Spec sections to provide to Claude Code:**
- Detection Signals → Signal 1 (full rule-based section including filler phrase list, regex patterns, and short text handling)
- SQLite Schema → content table definition
- Architecture diagram → submission flow only

**What to ask Claude Code to generate:**
1. Flask app skeleton (`app.py`) with `POST /submit` route, request validation (missing fields, word count floor and ceiling), and a placeholder response structure
2. `rule_analyzer.py` — the full rule-based signal function returning `rule_score` (float) and `matched_patterns` (list), with the 150-word check at the top

**How to verify before wiring into the endpoint:**
Run `rule_analyzer.py` directly on three inputs:
- A paragraph of obvious AI filler text → should score above 0.5 and return matched phrases
- A personal anecdote with no filler → should score below 0.3 with empty matched list
- A 50-word input → should trigger the short text rejection before scoring runs

---

### M4 — Second Signal + Confidence Scoring

**Spec sections to provide to Claude Code:**
- Detection Signals → Signal 2 (full Groq section including exact anchored prompt and unavailability behavior)
- Uncertainty Representation (full section including thresholds and disagreement check)
- Architecture diagram → pipeline section

**What to ask Claude Code to generate:**
1. `groq_analyzer.py` — Groq API call with the exact anchored prompt, JSON response parsing, 10-second timeout, and 503 response if Groq is unavailable
2. `confidence.py` — disagreement check, weighted average, and band mapping

**What to check:**
Run the full pipeline (both signals + confidence scorer) on:
- Known AI text → should score above 0.65, band = "high_confidence_ai"
- Known human text → should score below 0.35, band = "high_confidence_human"
- A borderline case → should land in uncertain band (0.35–0.65)
- Kill the Groq connection → 503 returned, no crash, no partial result issued

---

### M5 — Production Layer

**Spec sections to provide to Claude Code:**
- Transparency Label Variants (all three exact strings)
- Appeals Workflow (full section)
- SQLite Schema (both tables)
- Rate Limiting (all limits and reasoning)
- Architecture diagram (all three flows)

**What to ask Claude Code to generate:**
1. `label_generator.py` — maps confidence band string to exact label text
2. `db.py` — SQLite setup, table creation, insert and query functions for both tables
3. `POST /appeal` route — all four validation checks, status update, appeals table insert, response
4. `GET /appeals` route — JOIN query returning under_review appeals with original decision context
5. `GET /log` route — returns all content table rows with optional `?limit=n` filter
6. Rate limiting via `flask-limiter` on submit and appeal endpoints

**How to verify:**
- Submit text and confirm all three label variants are reachable by producing each confidence band
- Submit an appeal and confirm `appeal_status` changes to "under_review" in `GET /appeals`
- Submit an appeal with no reasoning → confirm 400 returned
- Submit a second appeal on the same content_id → confirm 400 returned
- Submit 6 requests in one minute → confirm the 6th returns 429
- Check `GET /log` shows at least 3 entries with correct fields

---

## File Structure

```
provenance-guard/
├── planning.md
├── README.md
├── app.py                    ← Flask app, all route definitions
├── pipeline/
│   ├── __init__.py
│   ├── rule_analyzer.py      ← filler phrases, em-dash, parallel structures
│   ├── groq_analyzer.py      ← Groq API call, anchored prompt, timeout, 503
│   └── confidence.py         ← disagreement check, weighted avg, band mapping
├── labels/
│   └── generator.py          ← band string → exact label text
├── db/
│   └── database.py           ← SQLite setup, table creation, insert/query helpers
├── appeals/
│   └── handler.py            ← validation, status update, appeals table insert
├── middleware/
│   └── rate_limiter.py       ← flask-limiter config, per-IP and per-content limits
├── requirements.txt
└── .env.example              ← GROQ_API_KEY placeholder
```