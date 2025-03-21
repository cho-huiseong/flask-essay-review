import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai

# 🔹 환경 변수에서 API 키 가져오기 (보안 문제 해결)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("🚨 환경 변수 'OPENAI_API_KEY'가 설정되지 않았습니다!")

# 🔹 OpenAI 클라이언트 생성
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# 🔹 Flask 앱 생성 및 CORS 설정 (웹사이트에서 API 호출 가능)
app = Flask(__name__)
CORS(app)

# 🔹 논술문 첨삭 API
@app.route("/review", methods=["POST"])
def review():
    try:
        data = request.json
        essay_text = data.get("essay", "")

        if not essay_text.strip():
            return jsonify({"error": "논술문을 입력하세요."}), 400

        # OpenAI API 호출
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "You are a professional writing tutor."},
                {"role": "user", "content": f"학생의 논술문을 첨삭하세요:\n\n{essay_text}"}
            ]
        )

        feedback = response.choices[0].message["content"]
        return jsonify({"feedback": feedback})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
