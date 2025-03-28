from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import os

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/review', methods=['POST'])
def review_essay():
    data = request.get_json()
    passage = data.get("passage", "")
    question = data.get("question", "")
    essay = data.get("essay", "")

    # 사용자 정의 체점 기준 적용
    system_prompt = (
        "너는 고등학생 논술문을 평가하는 논술 첨삭 전문가야.\n"
        "다음 체점 기준에 따라 학생의 글을 평가하고, 각 항목에 대해 10점 만점의 점수와 구체적인 피드백을 제공해줘.\n\n"
        "[채점 기준]\n"
        "1. 첫 문장에서 논제가 요구하는 질문에 대한 답을 밝혔는가? (이해력)\n"
        "2. 제시문에 기반한 사실과 정보 만으로 요약하였는가? (독해력)\n"
        "3. 제시문끼리 연결할 수 있는 기능 문장으로 맥락을 잘 이었는가?\n"
        "4. 논제가 요구한 질문의 답에 대해 알맞은 까닭을 들었는가?\n"
        "5. 채점 기준 순서대로 문장을 배열하였는가?\n"
        "6. 적절한 어휘를 사용하였는가?\n\n"
        "각 항목별 점수(10점 만점)와 평가 코멘트를 작성하고, 마지막에 총평을 작성해줘.\n"
        "총평 아래에는 학생이 참고할 수 있도록 예시 문단도 함께 작성해줘.\n"
        "전체 톤은 친절하고 명확하게, 선생님이 학생에게 피드백을 주는 말투로 해줘."
    )

    user_prompt = f"""
[제시문]
{passage}

[질문]
{question}

[학생의 논술문]
{essay}
"""

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=1000,
        temperature=0.7
    )

    feedback = response.choices[0].message.content.strip()
    return jsonify({"feedback": feedback})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
