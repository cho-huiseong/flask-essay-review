# ✅ 다쓰 리포트용 최종 app.py
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import openai
import os

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")  # 환경변수에서 키를 가져오도록 설정

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/review", methods=["POST"])
def review():
    data = request.get_json()
    passages = data.get("passages", [])
    question = data.get("question", "")
    essay = data.get("essay", "")

    # 제시문 정리
    labels = ['가','나','다','라','마','바']
    passage_text = "\n".join([f"제시문 <{labels[i]}>: {p}" for i, p in enumerate(passages)])

    # GPT 프롬프트 구성
    prompt = f"""
    아래는 초등학생이 논술문을 작성하기 위한 제시문과 질문, 그리고 작성된 논술문입니다.
    - 제시문:
    {passage_text}

    - 질문:
    {question}

    - 논술문:
    {essay}

    위 내용을 바탕으로 학생이 논술문을 더 잘 쓸 수 있도록 예시답안을 작성해 주세요.
    반드시 아래 형식을 따라주세요:
    [예시답안]
    예시답안 내용을 여기에 작성
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "당신은 초등 논술 선생님입니다. 친절하고 구체적으로 안내하세요."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        full_response = response.choices[0].message.content

        # [예시답안] 파트만 추출
        example = full_response.split("[예시답안]")[-1].strip()

        # 샘플 점수 (랜덤 또는 향후 추출 로직 가능)
        score = [7, 8, 6, 9, 7, 8]

        return jsonify({"answer": example, "chart": score})

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(debug=True)
