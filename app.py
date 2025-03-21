import openai
import os
from flask import Flask, request, jsonify

app = Flask(__name__)

# 환경 변수에서 API 키 가져오기
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("🚨 OPENAI_API_KEY가 설정되지 않았습니다. Render 환경 변수를 확인하세요.")

openai.api_key = OPENAI_API_KEY

@app.route('/review', methods=['POST'])
def review_essay():
    try:
        data = request.get_json()
        essay_text = data.get("essay")

        if not essay_text:
            return jsonify({"error": "논술문이 입력되지 않았습니다."}), 400

        # GPT-4 API 호출
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an AI writing evaluator."},
                {"role": "user", "content": f"다음 논술문을 평가하고 피드백을 제공해 주세요: {essay_text}"}
            ]
        )

        feedback = response["choices"][0]["message"]["content"]
        return jsonify({"feedback": feedback})

    except openai.error.OpenAIError as e:
        return jsonify({"error": f"OpenAI API 오류 발생: {str(e)}"}), 500

    except Exception as e:
        return jsonify({"error": f"서버 내부 오류: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
