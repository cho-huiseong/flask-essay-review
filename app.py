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
학생이 쓴 글을 아래의 기준에 따라 평가하고, 각 항목별 점수와 그 이유를 학생에게 친절하게 설명해주세요.
존댓말을 사용하시고, 따뜻한 말투로 구체적인 피드백을 주세요.
그리고 마지막에, 이 학생이 더 잘 쓸 수 있도록 예시답안을 작성해주세요.

[평가 기준 안내]
- 논리력: 주제를 명확히 전달하고 주장과 사실을 구분했는지
- 독해력: 제시문 내용을 바탕으로 적절한 근거를 들었는지
- 구성력: 논제에 맞는 서론-본론-결론 구조를 갖추었는지
- 표현력: 문법과 맞춤법, 어휘를 적절히 사용했는지

[입력 자료]
제시문:
{passage_text}

질문:
{question}

논술문:
{essay}

위 기준에 따라 다음 형식으로 답변해 주세요:

[평가]
[논리력]
점수: (숫자)점
이유: ~

[독해력]
점수: (숫자)점
이유: ~

[구성력]
점수: (숫자)점
이유: ~

[표현력]
점수: (숫자)점
이유: ~

[예시답안]
(학생이 참고할 수 있는 논술문 예시)
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "당신은 초등 논술 선생님입니다. 평가와 예시답안을 친절하고 구체적으로 작성합니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1500
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
