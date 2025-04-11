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
    print("✅ 받은 데이터:", data)

    passages = data.get("passages", [])
    question = data.get("question", "")
    essay = data.get("essay", "")

    labels = ['가','나','다','라','마','바']
    passage_text = "\n".join([f"제시문 <{labels[i]}>: {p}" for i, p in enumerate(passages)])

    # 강력한 프롬프트 정의
    prompt = f"""
당신은 초등학생을 가르치는 논술 선생님입니다.

다음은 각 항목에 대한 정의입니다. 이 정의에 맞춰 평가해 주세요.

[논리력]
- 논제가 묻는 내용을 **명확히 답변**했는지, **주장을 분명히 제시**했는지 평가합니다.

[독해력]
- 제시문에 있는 **정보만 사용**하여 논지를 전개했는지, 제시문을 **올바르게 분석**했는지 평가합니다.

[구성력]
- 문단 구분이 **명확하고**, 논리적 흐름이 **자연스럽게 이어졌는지** 평가합니다.

[표현력]
- 문법에 맞는 **문장**을 사용했는지, **적절한 어휘**와 **맞춤법**을 사용했는지 평가합니다.

학생이 쓴 글을 다음 기준에 따라 평가해 주세요. 각 항목에 대해 점수와 구체적인 이유를 써 주세요. 예시답안도 작성해 주세요.

[논리력]
점수: (숫자, 예: 8)
이유: (구체적 설명)

[독해력]
점수: (숫자, 예: 9)
이유: (구체적 설명)

[구성력]
점수: (숫자, 예: 7)
이유: (구체적 설명)

[표현력]
점수: (숫자, 예: 10)
이유: (구체적 설명)

[예시답안]
(학생의 글투와 어체로 작성)

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
        print("💬 GPT 응답 원문:\n", content)

        sections = {"논리력": {}, "독해력": {}, "구성력": {}, "표현력": {}, "예시답안": ""}
        current = None

        # 응답을 파싱하여 점수와 이유를 얻음
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
                    except Exception as e:
                        print(f"⚠️ 점수 파싱 실패: {line}", e)
                        sections[current]["score"] = 0  # 점수 파싱 실패 시 기본값 0
                elif "이유" in line:
                    sections[current]["reason"] = line.split(":", 1)[-1].strip() if ":" in line else "이유 없음"  # 이유 없을 경우 기본값 설정
            elif current == "예시답안":
                sections[current] += line + "\n"

        # 점수와 이유를 응답으로 반환
        return jsonify({
            "scores": [sections[k].get("score", 0) for k in ["논리력", "독해력", "구성력", "표현력"]],
            "reasons": {k: sections[k].get("reason", "") for k in ["논리력", "독해력", "구성력", "표현력"]},
            "example": sections["예시답안"].strip()
        })

    except Exception as e:
        print("❌ 처리 중 오류 발생:", str(e))
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(debug=True)
