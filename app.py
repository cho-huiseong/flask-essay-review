from flask import Flask, request, jsonify, render_template
import openai
import os

app = Flask(__name__)

# 🔹 Render 환경변수에서 OPENAI_API_KEY 가져오기
openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route("/review", methods=["GET", "POST"])
def review_essay():
    if request.method == "GET":
        return render_template("index.html")  # 🔹 웹 UI 제공

    data = request.get_json()
    if not data or "essay" not in data:
        return jsonify({"error": "No essay provided"}), 400

    essay_text = data["essay"]

    # 🔹 GPT-4 API 호출하여 논술문 평가 및 피드백 제공
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": """
            You are an expert in academic writing and critical analysis.
            Evaluate the given essay based on the following criteria:
            1. **Grammar & Clarity**: Check for grammatical errors and sentence clarity.
            2. **Logical Flow**: Assess how well the arguments are structured.
            3. **Critical Thinking**: Determine the level of critical thinking demonstrated.
            4. **Creativity**: Evaluate originality and innovative perspectives in the essay.
            5. **Persuasiveness**: Assess how convincing the arguments are.
            
            Provide a detailed feedback including strengths and areas of improvement.
            """},
            {"role": "user", "content": f"Here is the student's essay:\n\n{essay_text}"}
        ],
        max_tokens=700  # 🔹 충분한 답변 길이 설정
    )

    feedback = response["choices"][0]["message"]["content"]

    return jsonify({"feedback": feedback})  # 🔹 GPT-4의 첨삭 결과 반환

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
