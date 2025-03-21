import os
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/review", methods=["POST"])
def review_essay():
    data = request.get_json()
    if not data or "essay" not in data:
        return jsonify({"error": "No essay provided"}), 400

    essay_text = data["essay"]
    feedback = f"GPT-4 Feedback: {essay_text}"  # AI 피드백 로직

    return jsonify({"feedback": feedback})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # Render에서 자동 할당된 포트 사용
    app.run(host="0.0.0.0", port=port, debug=True)
