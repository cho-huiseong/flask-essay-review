from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

@app.route("/review", methods=["GET", "POST"])
def review_essay():
    if request.method == "GET":
        return render_template("index.html")  # 🔹 GET 요청 시 index.html을 반환

    data = request.get_json()
    if not data or "essay" not in data:
        return jsonify({"error": "No essay provided"}), 400

    essay_text = data["essay"]
    feedback = f"GPT-4 Feedback: {essay_text}"

    return jsonify({"feedback": feedback})

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
