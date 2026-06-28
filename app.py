import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from db.database import get_appeals, get_content_by_id, get_log, init_db, insert_appeal, insert_content, update_appeal_status
from pipeline import confidence as confidence_scorer
from pipeline.groq_analyzer import analyze as groq_analyze
from pipeline.rule_analyzer import analyze as rule_analyze

load_dotenv()

app = Flask(__name__)
init_db()

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429


@app.route("/submit", methods=["POST"])
@limiter.limit("5 per minute;20 per day")
def submit():
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    creator_id = (body.get("creator_id") or "").strip()

    if not text or not creator_id:
        missing = [f for f, v in [("text", text), ("creator_id", creator_id)] if not v]
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        rule_score, matched_patterns = rule_analyze(text)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        groq_result = groq_analyze(text)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    groq_score = groq_result["groq_score"]
    groq_reasoning = groq_result["reasoning"]

    conf = confidence_scorer.score(rule_score, groq_score)

    content_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    response = {
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": conf["confidence_band"],
        "confidence": conf["final_score"],
        "label": conf["label_text"],
        "signals": {
            "rule_score": rule_score,
            "matched_patterns": matched_patterns,
            "groq_score": groq_score,
            "groq_reasoning": groq_reasoning,
            "redundancy": groq_result["redundancy"],
            "empty_praise": groq_result["empty_praise"],
            "undeveloped_ideas": groq_result["undeveloped_ideas"],
            "signals_agree": conf["signals_agree"],
        },
        "status": "classified",
        "timestamp": timestamp,
    }

    insert_content({
        "content_id": content_id,
        "creator_id": creator_id,
        "ip": request.remote_addr,
        "timestamp": timestamp,
        "word_count": len(text.split()),
        "text": text,
        "rule_score": rule_score,
        "matched_patterns": matched_patterns,
        "groq_score": groq_score,
        "groq_reasoning": groq_reasoning,
        "final_score": conf["final_score"],
        "confidence_band": conf["confidence_band"],
        "label_text": conf["label_text"],
        "appeal_status": "reviewed",
    })

    return jsonify(response), 200


@app.route("/appeal", methods=["POST"])
@limiter.limit("3 per day")
def appeal():
    body = request.get_json(silent=True) or {}
    content_id = body.get("content_id")
    creator_id = body.get("creator_id")
    creator_reasoning = (body.get("creator_reasoning") or "").strip()

    if not content_id:
        return jsonify({"error": "content_id is required"}), 400
    if not creator_reasoning:
        return jsonify({"error": "creator_reasoning is required"}), 400

    matched = get_content_by_id(content_id)
    if matched is None:
        return jsonify({"error": "content not found"}), 404
    if matched["appeal_status"] == "under_review":
        return jsonify({"error": "an appeal has already been submitted for this content"}), 400

    appeal_id = str(uuid.uuid4())
    appeal_timestamp = datetime.now(timezone.utc).isoformat()

    update_appeal_status(content_id, "under_review")
    insert_appeal({
        "appeal_id": appeal_id,
        "content_id": content_id,
        "creator_id": creator_id,
        "creator_reasoning": creator_reasoning,
        "appeal_timestamp": appeal_timestamp,
    })

    return jsonify({
        "appeal_id": appeal_id,
        "content_id": content_id,
        "status": "under_review",
        "message": "Your appeal has been received. The original decision has been flagged for human review.",
        "timestamp": appeal_timestamp,
    }), 200


@app.route("/appeals", methods=["GET"])
@limiter.limit("30 per minute")
def appeals():
    rows = get_appeals()
    result = []
    for row in rows:
        result.append({
            "appeal_id": row["appeal_id"],
            "content_id": row["content_id"],
            "creator_id": row["creator_id"],
            "creator_reasoning": row["creator_reasoning"],
            "appeal_timestamp": row["appeal_timestamp"],
            "original_decision": {
                "text": row["text"],
                "rule_score": row["rule_score"],
                "matched_patterns": row["matched_patterns"],
                "groq_score": row["groq_score"],
                "groq_reasoning": row["groq_reasoning"],
                "final_score": row["final_score"],
                "confidence_band": row["confidence_band"],
                "label_text": row["label_text"],
                "timestamp": row["timestamp"],
            },
        })
    return jsonify({"appeals": result}), 200


@app.route("/log", methods=["GET"])
@limiter.limit("30 per minute")
def log():
    return jsonify({"entries": get_log(limit=20)}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5001)
