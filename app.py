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

[논리력] 논제가 물어본 것에 답했는가? 주장을 밝혔는가? 주장에 적절한 까닭을 밝혔는가?
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
@app.route('/example', methods=['POST'])
def example():
    data = request.json
    passages = data.get('passages', [])
    question = data.get('question', '')
    essay = data.get('essay', '')

    try:
        char_base = int(data.get('charBase', 600))
        char_range = int(data.get('charRange', 100))
    except (TypeError, ValueError):
        char_base = 600
        char_range = 100

    prompt = f"""
아래는 학생이 작성한 논술문입니다. 이 글을 바탕으로 다음 작업을 수행해 주십시오.

1. 학생의 논술문을 참고하여, 고등학교 교사의 입장에서 예시답안을 작성하십시오.
   - 말투는 고등학교 교사처럼 단정하고 엄격하게 유지하십시오.
   - 예시답안은 충분히 구체적이고 논리적으로 작성하며, 최소 500자 이상 권장합니다.

2. 작성된 예시답안과 학생의 논술문을 비교하여 다음 세 항목을 모두 포함해 주십시오:
   - (1) 어떤 부분이 수정되었는가
   - (2) 그 부분이 왜 수정될 필요가 있었는가
   - (3) 수정 후 어떻게 개선되었는가
   - 비교 설명은 반드시 300자 이상, 1000자 이하로 작성하십시오.

3. 다음 JSON 형식에 맞추어 정확하게 응답하십시오. key 이름과 구조를 절대로 바꾸지 마십시오. 설명 문구를 추가하지 마시고 JSON만 출력하십시오.

{
  "example": "예시답안을 여기에 작성하십시오. 반드시 실제 예시 내용을 작성해 주십시오.",
  "comparison": "비교 설명을 여기에 작성하십시오. 300~1000자 분량의 실제 분석 내용을 입력하십시오."
}

제시문:
{chr(10).join(passages)}

질문:
{question}

학생의 논술문:
{essay}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{ "role": "user", "content": prompt }],
            temperature=0.7
        )
        raw = response.choices[0].message.content
        parsed = json.loads(raw)

        return jsonify({
            "example": parsed.get("example", ""),
            "comparison": parsed.get("comparison", "")
        })

    except Exception as e:
        return jsonify({ "error": str(e) }), 500
