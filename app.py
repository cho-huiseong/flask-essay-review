from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import os
import re
import json

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
        print("❗예외 발생 (전체 try):", str(e), flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/example", methods=["POST"])
def example():
    data = request.json
    passages = data.get('passages', [])
    question = data.get('question', '')
    essay = data.get('essay', '')
    retry = data.get('retryConfirmed', False)

    try:
        char_base = int(data.get('charBase')) if data.get('charBase') else 600
        char_range = int(data.get('charRange')) if data.get('charRange') else 100
    except (TypeError, ValueError):
        char_base = 600
        char_range = 100

    min_chars = char_base - char_range
    if retry:
        min_chars += 100
        print(f"🔁 재요청으로 기준 글자 수 증가: {min_chars}자 이상")
        max_attempt = 1
    else:
        max_attempt = 2

    print(f"✅ 최소 글자 수 기준: {min_chars}")

    initial_user_prompt = f"""
아래는 학생이 작성한 논술문입니다. 이 글을 바탕으로 다음 작업을 수행해 주십시오:

... (중략: 동일 프롬프트 그대로 유지)

제시문:
{chr(10).join(passages)}

질문:
{question}

학생의 논술문:
{essay}
"""

    messages = [
        {"role": "system", "content": "너는 고등학생 논술 답안을 만드는 선생님이야. 위 지침에 따라 예시답안을 작성해."},
        {"role": "user", "content": initial_user_prompt}
    ]

    example_text = ""
    for attempt in range(max_attempt):
        res = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=messages,
            temperature=0.7,
            max_tokens=2000
        )
        content = res.choices[0].message.content
        print("🧾 GPT 응답 원문:\n", content)

        try:
            parsed = json.loads(content)
            new_example = parsed.get("example", "")
            print("✅ 예시답안 글자 수:", len(new_example))

            if len(new_example) >= min_chars:
                example_text = new_example
                break

            messages.append({"role": "assistant", "content": new_example})
            messages.append({
                "role": "user",
                "content": (
                    f"이전 예시답안은 {len(new_example)}자입니다. 아래 조건을 지켜 다시 작성하십시오:\n"
                    f"- 반드시 {min_chars}자 이상 작성하십시오\n"
                    f"- 내용 중복 없이 주장, 근거, 예시를 확장하십시오\n"
                    f"- 논리 흐름, 문체는 유지하십시오\n"
                    f"👉 목표 글자 수: {len(new_example) + 100}자 이상"
                )
            })

        except json.JSONDecodeError as e:
            print("❌ JSON 파싱 실패:\n", content)
            continue

    example_text = new_example
    return jsonify({
        "example": example_text,
        "comparison": parsed.get("comparison", ""),
        "length_valid": len(example_text) >= min_chars,
        "length_actual": len(example_text)
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
