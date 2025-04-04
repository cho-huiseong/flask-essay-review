from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import openai
import os

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/review", methods=["POST"])
def review():
    data = request.get_json()
    passages = data.get("passages", [])
    question = data.get("question", "")
    essay = data.get("essay", "")

    labels = ['가','나','다','라','마','바']
    passage_text = "\n".join([f"제시문 <{labels[i]}>: {p}" for i, p in enumerate(passages)])

    prompt = f"""
당신은 초등학생을 가르치는 논술 선생님입니다.

학생의 글을 다음 4가지 기준에 따라 평가하고, 각 항목에 대해 아래 형식을 반드시 지켜서 출력해 주세요:

[논리력]
점수: (숫자만, 예: 8)
이유: ~

[독해력]
점수: (숫자만, 예: 9)
이유: ~

[구성력]
점수: (숫자만, 예: 7)
이유: ~

[표현력]
점수: (숫자만, 예: 10)
이유: ~

그리고 마지막에 아래 형식 그대로 예시답안을 제공해 주세요:

[예시답안]
(여기에 글)

주의사항:
- 반드시 위의 출력 형식을 지켜 주세요 (항목 이름, 점수, 이유, 줄 순서까지).
- 점수는 숫자만 적어 주세요. "점"이나 다른 말은 붙이지 마세요.
- 각 섹션은 대괄호로 시작해야 합니다.

--- 입력자료 ---

제시문:
{passage_text}

질문:
{question}

논술문:
{essay}
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "당신은 초등 논술 선생님입니다. 평가와 예시답안을 친절하고 구체적으로 작성합니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1800
        )

        content = response.choices[0].message.content

        sections = {"논리력": {}, "독해력": {}, "구성력": {}, "표현력": {}, "예시답안": ""}
        current = None

        for line in content.splitlines():
            line = line.strip()
            if line.startswith("[논리력]"): current = "논리력"
            elif line.startswith("[독해력]"): current = "독해력"
            elif line.startswith("[구성력]"): current = "구성력"
            elif line.startswith("[표현력]"): current = "표현력"
            elif line.startswith("[예시답안]"): current = "예시답안"
            elif current and current != "예시답안":
                if line.startswith("점수:"):
                    sections[current]["score"] = int(''.join(filter(str.isdigit, line)))
                elif line.startswith("이유:"):
                    sections[current]["reason"] = line.replace("이유:", "").strip()
            elif current == "예시답안":
                sections[current] += line + "\n"

        return jsonify({
            "scores": [sections[k]["score"] for k in ["논리력", "독해력", "구성력", "표현력"]],
            "reasons": {k: sections[k]["reason"] for k in ["논리력", "독해력", "구성력", "표현력"]},
            "example": sections["예시답안"].strip()
        })

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(debug=True)
