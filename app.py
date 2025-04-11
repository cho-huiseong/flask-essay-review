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

# 평가 요청
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

[논리력] 논제가 물어본 것에 답했는가? 주장을 밝혔는가?  
[독해력] 제시문에 있는 내용으로만 구성되었는가? 제시문 분석이 올바르게 이루어졌는가?  
[구성력] 문단 들여쓰기, 구분이 확실하게 되어 있는가? 논리적 흐름이 방해되지 않는가?  
[표현력] 문법에 맞는 문장을 구사했는가? 적절한 어휘를 사용했는가? 맞춤법 표기가 틀리지 않았는가?

---

제시문:
{passage_text}

질문:
{question}

논술문:
{essay}

---

❗ 아래 형식을 반드시 그대로 지켜서 작성해 주세요:

[논리력]  
점수: (0~10 사이의 정수만)  
이유: (한 문장 이상 구체적으로 작성)  

[독해력]  
점수: (정수만)  
이유: ...

[구성력]  
점수: (정수만)  
이유: ...

[표현력]  
점수: (정수만)  
이유: ...

예시:
[논리력]  
점수: 8  
이유: 논제를 정확히 이해했고 중심 주장이 분명하게 드러남

❗ 다른 형식은 사용하지 말고 위와 같이 **숫자 점수와 이유를 항목별로 분리해서** 반드시 작성하세요.  
예시답안은 지금 작성하지 마세요.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "너는 초등 논술 첨삭 선생님이야. 평가 기준에 따라 평가만 작성해."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1500
        )

        content = response.choices[0].message.content
        print("\n📥 GPT 평가 응답:\n", content)

        sections = {"논리력": {}, "독해력": {}, "구성력": {}, "표현력": {}}
        current = None

        for line in content.splitlines():
            line = line.strip()
            if line.startswith("[논리력]"): current = "논리력"
            elif line.startswith("[독해력]"): current = "독해력"
            elif line.startswith("[구성력]"): current = "구성력"
            elif line.startswith("[표현력]"): current = "표현력"
            elif current:
                if "score" not in sections[current]:
                    score_match = re.search(r"(\d{1,2})", line)
                    if score_match:
                        sections[current]["score"] = int(score_match.group(1))
                if "이유" in line:
                    sections[current]["reason"] = line.split(":", 1)[-1].strip()
                elif "reason" not in sections[current]:
                    sections[current]["reason"] = line

        for k in sections:
            sections[k].setdefault("score", 0)
            sections[k].setdefault("reason", "이유 없음")

        return jsonify({
            "scores": [sections[k]["score"] for k in ["논리력", "독해력", "구성력", "표현력"]],
            "reasons": {k: sections[k]["reason"] for k in ["논리력", "독해력", "구성력", "표현력"]}
        })

    except Exception as e:
        return jsonify({"error": str(e)})

# 예시답안 요청
@app.route("/example", methods=["POST"])
def example():
    data = request.get_json()
    passages = data.get("passages", [])
    question = data.get("question", "")
    essay = data.get("essay", "")
    scores = data.get("scores", [])
    reasons = data.get("reasons", {})
    char_base = data.get("charBase", "700")
    char_range = data.get("charRange", "50")

    labels = ['가','나','다','라','마','바']
    passage_text = "\n".join([f"제시문 <{labels[i]}>: {p}" for i, p in enumerate(passages)])

    평가요약 = "\n".join([
        f"[{k}] {scores[i]}점 - {reasons.get(k, '')}"
        for i, k in enumerate(["논리력", "독해력", "구성력", "표현력"])
    ])

    prompt = f"""
너는 초등학생 논술문을 첨삭하는 선생님이야.

아래는 학생이 작성한 논술문에 대한 평가 요약이야:
{평가요약}

이제 아래 조건에 따라 예시답안을 작성해줘.

[조건]
- 아래 논술문을 참고해서, 평가 결과를 반영해 더 나은 예시답안을 작성할 것
- 글자 수: {char_base} ± {char_range}자 (공백 포함 기준)
- 학생 말투 그대로 유지
- 절대 요약하지 말고 풍부하게 작성할 것

---

제시문:
{passage_text}

질문:
{question}

논술문:
{essay}

※ 지금은 예시답안만 작성해주세요.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "너는 초등학생에게 논술 예시답안을 작성해주는 선생님이야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1200
        )

        content = response.choices[0].message.content
        print("\n📝 GPT 예시답안 응답:\n", content)

        return jsonify({"example": content.strip()})

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(debug=True)
