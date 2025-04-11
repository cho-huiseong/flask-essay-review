from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import os
import re

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

    try:
        base = int(char_base)
        delta = int(char_range)
        min_chars = base - delta
        max_chars = base + delta
    except:
        min_chars = 0
        max_chars = 9999

    prompt = f"""
당신은 초등학생을 가르치는 논술 선생님입니다.

다음은 논술 평가 기준입니다:

[논리력]
- 논제가 묻는 내용을 정확히 이해하고 답했는지,
- 주장을 명확히 밝혔는지 평가합니다.

[독해력]
- 제시문에 포함된 정보만을 사용했는지,
- 제시문을 올바르게 분석하고 활용했는지 평가합니다.

[구성력]
- 문단 구분이 명확하게 되어 있는지,
- 논리적인 흐름이 자연스럽게 이어졌는지,
- 글자 수 제한({min_chars}~{max_chars}자, 공백 포함 기준)를 지켰는지도 평가에 포함됩니다.

[표현력]
- 문법에 맞는 문장을 사용했는지,
- 맞춤법과 띄어쓰기를 지켰는지,
- 적절한 어휘와 문장 길이를 사용했는지 평가합니다.

---

❗ 다음의 절차를 반드시 지켜서 작업하세요:

1. 위 네 가지 평가 항목에 대해 각각 점수(10점 만점)와 구체적인 이유를 작성합니다.  
   생략하지 말고 각 항목마다 정확하게 작성해 주세요.

2. 예시답안을 작성합니다. 다음 기준을 반드시 지켜 주세요:
  - 글자 수: 최소 {min_chars}자 이상, 최대 {max_chars}자 이하  
    ✅ 이 글자 수는 **공백 포함 기준**이며, 띄어쓰기도 1자로 계산됩니다.
  - 말투: 학생의 논술문과 동일한 말투, 어투, 문장 스타일, 어휘 수준 유지
  - GPT의 일반적인 말투(공손한 설명체) 사용 금지
  - 절대로 요약하지 말고, 풍부하고 충분하게 작성할 것

※ 평가와 예시답안은 모두 리포트에 포함되어야 하며, 하나라도 생략되면 부적절한 결과입니다.

---

[제시문]
{passage_text}

[질문]
{question}

[논술문]
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
            max_tokens=2000
        )

        print("\n🔎 GPT 응답 시작 ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓")
        print(response.choices[0].message.content)
        print("🔎 GPT 응답 끝 ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑\n")

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
                    score_match = re.search(r"(\d{1,2})", line)
                    if score_match:
                        sections[current]["score"] = int(score_match.group(1))
                elif "이유" in line:
                    reason_text = line.split(":", 1)[-1].strip() if ":" in line else line
                    sections[current]["reason"] = reason_text
                elif "score" not in sections[current] and "reason" not in sections[current]:
                    # 점수도 아니고 이유도 없지만 설명 줄일 경우 → 이유로 저장
                    sections[current]["reason"] = line
            elif current == "예시답안":
                sections[current] += line + "\n"

        # 모든 항목에 기본값 설정
        for key in ["논리력", "독해력", "구성력", "표현력"]:
            sections[key].setdefault("score", 0)
            sections[key].setdefault("reason", "이유 없음")

        return jsonify({
            "scores": [sections[k]["score"] for k in ["논리력", "독해력", "구성력", "표현력"]],
            "reasons": {k: sections[k]["reason"] for k in ["논리력", "독해력", "구성력", "표현력"]},
            "example": sections["예시답안"].strip()
        })

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(debug=True)
