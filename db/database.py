import json
import os
import sqlite3

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "provenance.db")

_CREATE_CONTENT = """
CREATE TABLE IF NOT EXISTS content (
    content_id      TEXT PRIMARY KEY,
    creator_id      TEXT,
    ip              TEXT,
    timestamp       TEXT,
    word_count      INTEGER,
    text            TEXT,
    rule_score      REAL,
    matched_patterns TEXT,
    groq_score      REAL,
    groq_reasoning  TEXT,
    final_score     REAL,
    confidence_band TEXT,
    label_text      TEXT,
    appeal_status   TEXT DEFAULT 'reviewed'
)
"""

_CREATE_APPEALS = """
CREATE TABLE IF NOT EXISTS appeals (
    appeal_id        TEXT PRIMARY KEY,
    content_id       TEXT,
    creator_id       TEXT,
    creator_reasoning TEXT,
    appeal_timestamp TEXT,
    FOREIGN KEY (content_id) REFERENCES content(content_id)
)
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(_CREATE_CONTENT)
        conn.execute(_CREATE_APPEALS)
        conn.commit()


def insert_content(record: dict) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO content (
                content_id, creator_id, ip, timestamp, word_count, text,
                rule_score, matched_patterns, groq_score, groq_reasoning,
                final_score, confidence_band, label_text, appeal_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.get("content_id"),
                record.get("creator_id"),
                record.get("ip"),
                record.get("timestamp"),
                record.get("word_count"),
                record.get("text"),
                record.get("rule_score"),
                json.dumps(record.get("matched_patterns", [])),
                record.get("groq_score"),
                record.get("groq_reasoning"),
                record.get("final_score"),
                record.get("confidence_band"),
                record.get("label_text"),
                record.get("appeal_status", "reviewed"),
            ),
        )
        conn.commit()


def insert_appeal(record: dict) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO appeals (appeal_id, content_id, creator_id, creator_reasoning, appeal_timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.get("appeal_id"),
                record.get("content_id"),
                record.get("creator_id"),
                record.get("creator_reasoning"),
                record.get("appeal_timestamp"),
            ),
        )
        conn.commit()


def get_appeals() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                a.appeal_id, a.content_id, a.creator_id, a.creator_reasoning, a.appeal_timestamp,
                c.text, c.rule_score, c.matched_patterns, c.groq_score, c.groq_reasoning,
                c.final_score, c.confidence_band, c.label_text, c.timestamp
            FROM appeals a
            JOIN content c ON a.content_id = c.content_id
            WHERE c.appeal_status = 'under_review'
            """
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        try:
            d["matched_patterns"] = json.loads(d.get("matched_patterns") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["matched_patterns"] = []
        result.append(d)
    return result


def update_appeal_status(content_id: str, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE content SET appeal_status = ? WHERE content_id = ?",
            (status, content_id),
        )
        conn.commit()


def get_content_by_id(content_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM content WHERE content_id = ?", (content_id,)
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    try:
        d["matched_patterns"] = json.loads(d.get("matched_patterns") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["matched_patterns"] = []
    return d


def get_log(limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM content ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        try:
            d["matched_patterns"] = json.loads(d.get("matched_patterns") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["matched_patterns"] = []
        result.append(d)
    return result
