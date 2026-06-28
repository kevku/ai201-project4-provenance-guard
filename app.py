import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from db.database import get_log, init_db, insert_content
from pipeline import confidence as confidence_scorer
from pipeline.groq_analyzer import analyze as groq_analyze
from pipeline.rule_analyzer import analyze as rule_analyze

load_dotenv()

app = Flask(__name__)
init_db()


@app.route("/submit", methods=["POST"])
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


@app.route("/log", methods=["GET"])
def log():
    return jsonify({"entries": get_log(limit=20)}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5001)
