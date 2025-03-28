from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import os

app = Flask(__name__)

# OpenAI client 설정 (환경변수에서 API 키 불러오는 방식 추천)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route('/')
def home():
    return render_template('index.html')  # 없으면 삭제해도 됨

@app.route('/review', methods=['POST', 'GET'])  # GET도 허용
def review_essay():
    if request.method == 'GET':
        return jsonify({"message": "GPT 논술 첨삭 API입니다. POST로 요청해주세요."})

    data = request.get_json()
    essay = data.get("essay", "")

    prompt = (
        "다음 논술문을 GPT-4-Turbo 기준으로 첨삭해주세요.\n"
        "비판적 사고, 창의성, 논리성, 설득력 등을 기준으로 평가해 주세요:\n\n" + essay
    )

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "당신은 글쓰기 평가 전문가입니다. 논술문을 친절하게 첨삭해 주세요."},
            {"role": "user", "content": prompt}
        ]
    )

    feedback = response.choices[0].message.content.strip()
    return jsonify({"feedback": feedback})

if __name__ == '__main__':
    app.run(debug=True)
