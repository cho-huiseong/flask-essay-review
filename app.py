from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import os

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/review", methods=["POST"])
def review():
    data = request.get_json()
    passages = data.get("passages", [])
    question = data.get("question", "")
    essay = data.get("essay", "")
    char_base = data.get("charBase")
    char_range = data.get("charRange")

    labels = ['가','나','다','라','마','바']
    passage_text = "\n".join([f"제시문 <{labels[i]}>: {p}" for i, p in enumerate(passages)])

    char_limit_instruction = ""
    if char_base and char_range:
        try:
            base = int(char_base)
            delta = int(char_range)
            char_limit_instruction = f"예시답안은 글자 수가 {base}±{delta}자 이내로 작성되어야 하며, 이를 넘지 않도록 주의해 주세요."
        except:
            pass

    prompt = f"""
당신은 초등학생을 가르치는 논술 선생님입니다.

다음은 평가 기준입니다:

[논리력]
- 논제가 묻는 내용을 명확히 답변했는지, 주장을 분명히 제시했는지 평가합니다.

[독해력]
- 제시문에 있는 정보만 사용하여 논지를 전개했는지, 제시문을 올바르게 분석했는지 평가합니다.

[구성력]
- 문단 구분이 명확하고, 논리적 흐름이 자연스럽게 이어졌는지 평가합니다.
- 글자 수 제한 ({char_base}±{char_range}자)가 주어졌다면, 이를 지켰는지도 평가에 반영합니다.

[표현력]
- 문법에 맞는 문장, 적절한 어휘, 맞춤법을 정확하게 사용했는지 평가합니다.

학생의 논술문을 다음 기준에 따라 평가해 주세요.
각 항목에 대해 점수와 구체적인 이유를 써 주세요.
그리고 {char_limit_instruction} 반드시 반영하여 예시답안을 작성해 주세요.

[논리력]
점수: (숫자)
이유: 

[독해력]
점수:
이유:

[구성력]
점수:
이유:

[표현력]
점수:
이유:

[예시답안]
(학생의 말투와 어투를 반영해 작성)

--- 입력자료 ---

제시문:
{passage_text}

질문:
{question}

논술문:
{essay}
"""

    try:
        response = client.chat.completions.create(
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
                if "점수" in line:
                    try:
                        score_line = ''.join(filter(str.isdigit, line))
                        sections[current]["score"] = int(score_line) if score_line else 0
                    except:
                        sections[current]["score"] = 0
                elif "이유" in line:
                    sections[current]["reason"] = line.split(":", 1)[-1].strip() if ":" in line else "이유 없음"
            elif current == "예시답안":
                sections[current] += line + "\n"

        return jsonify({
            "scores": [sections[k].get("score", 0) for k in ["논리력", "독해력", "구성력", "표현력"]],
            "reasons": {k: sections[k].get("reason", "") for k in ["논리력", "독해력", "구성력", "표현력"]},
            "example": sections["예시답안"].strip()
        })

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(debug=True)
