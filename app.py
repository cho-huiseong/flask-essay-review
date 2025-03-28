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

    system_prompt = (
        "너는 고등학생 대상 논술 첨삭 전문가야. 학생이 이해할 수 있도록 "
        "친절하고 구체적인 피드백을 제공해줘. "
        "논술문을 읽고 아래 항목에 따라 평가해:\n"
        "- 논리성\n- 구조\n- 표현력\n- 어휘 사용\n- 맞춤법/문법\n\n"
        "각 항목마다 10점 만점 점수와 구체적인 평가를 써줘.\n"
        "어색한 문장은 수정 예시를 포함해주고, 마지막엔 총평도 작성해줘.\n"
        "톤은 교사가 학생에게 조언하는 듯 부드럽고 명확하게 써줘."
    )

    user_prompt = f"""
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
        ]
    )

    feedback = response.choices[0].message.content.strip()
    return jsonify({"feedback": feedback})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
