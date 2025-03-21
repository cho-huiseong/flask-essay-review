from flask import Flask, request, jsonify
import json

app = Flask(__name__)

@app.route("/review", methods=["POST"])
def review_essay():
    data = request.get_json()
    if not data or "essay" not in data:
        return jsonify({"error": "No essay provided"}), 400

    essay_text = data["essay"]
    feedback = f"GPT-4 Feedback: {essay_text}"

    return app.response_class(
        response=json.dumps({"feedback": feedback}, ensure_ascii=False),  # 한글 깨짐 방지
        status=200,
        mimetype="application/json"
    )

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
