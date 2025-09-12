from flask import Flask, request, jsonify, render_template, make_response
from flask_cors import CORS
from openai import OpenAI
import os, re, json
# ==== Auth/DB ====
from datetime import datetime
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from passlib.hash import bcrypt

# ---------------------------------------------------------------------
# App & Config
# ---------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(int(os.environ.get("SESSION_COOKIE_SECURE", "0")))  # 1이면 True

CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------------------------------------------------------------------
# DB (SQLite 기본, POSTGRES_URL 있으면 Postgres)
# ---------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    engine = create_engine("sqlite:///app.db", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

class User(Base, UserMixin):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(120), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def set_password(self, raw):
        self.password_hash = bcrypt.hash(raw)

    def check_password(self, raw):
        try:
            return bcrypt.verify(raw, self.password_hash)
        except Exception:
            return False

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------
# Login manager
# ---------------------------------------------------------------------
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id: str):
    db = SessionLocal()
    try:
        return db.get(User, int(user_id))
    finally:
        db.close()

# ---------------------------------------------------------------------
# Routes: Pages
# ---------------------------------------------------------------------
@app.route("/")
def index():
    return make_response(render_template("index.html"))


# ---------------------------------------------------------------------
# Auth API
# ---------------------------------------------------------------------
def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()

@app.post("/auth/register")
def auth_register():
    data = request.get_json(force=True)
    email = _normalize_email(data.get("email"))
    password = (data.get("password") or "").strip()
    name = (data.get("name") or "").strip()

    if not email or not password or not name:
        return jsonify({"ok": False, "error": "필수 정보가 누락되었습니다."}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "error": "비밀번호는 6자 이상이어야 합니다."}), 400

    db = SessionLocal()
    try:
        if db.query(User).filter_by(email=email).first():
            return jsonify({"ok": False, "error": "이미 가입된 이메일입니다."}), 400
        user = User(email=email, name=name)
        user.set_password(password)
        db.add(user)
        db.commit()
        login_user(user, remember=True)
        return jsonify({"ok": True, "user": {"id": user.id, "email": user.email, "name": user.name}})
    finally:
        db.close()

@app.post("/auth/login")
def auth_login():
    data = request.get_json(force=True)
    email = _normalize_email(data.get("email"))
    password = (data.get("password") or "").strip()

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        if not user or not user.check_password(password):
            return jsonify({"ok": False, "error": "이메일 또는 비밀번호가 올바르지 않습니다."}), 401
        login_user(user, remember=True)
        return jsonify({"ok": True, "user": {"id": user.id, "email": user.email, "name": user.name}})
    finally:
        db.close()

@app.post("/auth/logout")
@login_required
def auth_logout():
    logout_user()
    return jsonify({"ok": True})

@app.get("/auth/me")
def auth_me():
    if current_user.is_authenticated:
        return jsonify({"ok": True, "user": {"id": current_user.id, "email": current_user.email, "name": current_user.name}})
    return jsonify({"ok": False, "user": None})

# ---------------------------------------------------------------------
# Review API
# ---------------------------------------------------------------------
@app.post("/review")
def review():
    data = request.get_json()
    passages = data.get("passages", [])
    question = data.get("question", "")
    essay = data.get("essay", "")

    labels = ['가','나','다','라','마','바','사','아','자','차']
    passage_text = "\n".join([f"제시문 <{labels[i]}>: {p}" for i, p in enumerate(passages)])

    prompt = f"""
당신은 초등학생을 가르치는 논술 선생님입니다.

다음은 논술 평가 기준입니다:

[논리력] 
- 논제가 요구한 질문에 정확히 답했는가?
- 글의 주장이 분명하게 드러났는가?
- 제시문을 활용하여 주장을 뒷받침했는가?
- 글 전체가 읽는 사람을 충분히 설득할 수 있을 만큼 논리적으로 전개되었는가?
- ❗ 근거가 없거나 근거가 약하거나, 설득력이 부족한 경우에는 반드시 크게 감점하라 (0~4점 이하).

[독해력] 
- 제시문 속 핵심 내용을 올바르게 요약하거나 인용했는가?
- 질문에 대한 답변이 글 속에서 명확하게 드러났는가?
- 제시문을 근거로 삼아 논지를 전개했는가?
- ❗ 제시문 외의 배경지식이나 외부 정보를 활용한 경우에는 반드시 크게 감점하라 (0~4점 이하).

[구성력] 
- 문단 구분과 들여쓰기가 잘 되어 있는가?
- 글 전체의 논리적 흐름이 자연스럽고 방해되지 않는가?

[표현력] 
- 문법에 맞는 문장을 구사했는가?
- 적절한 어휘를 사용했는가?
- 맞춤법이 틀리지 않았는가?
- 문장이 어색하거나 문법적으로 잘못된 경우(비문)는 감점하라.

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
이유: (한 문장 이상 구체적으로 작성)

[구성력]  
점수: (정수만)  
이유: (한 문장 이상 구체적으로 작성)

[표현력]  
점수: (정수만)  
이유: (한 문장 이상 구체적으로 작성)

❗ 다른 형식은 사용하지 말고 위와 같이 숫자 점수와 이유를 항목별로 분리해서 반드시 작성하세요.
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
                    prev = sections[current].get("reason", "")
                    sections[current]["reason"] = (prev + " " + line).strip()

        for k in sections:
            sections[k].setdefault("score", 0)
            sections[k].setdefault("reason", "이유 없음")

        return jsonify({
            "scores": [sections[k]["score"] for k in ["논리력", "독해력", "구성력", "표현력"]],
            "reasons": {k: sections[k]["reason"] for k in ["논리력", "독해력", "구성력", "표현력"]}
        })
    except Exception as e:
        print("❗예외 발생 (review):", str(e), flush=True)
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------------
# Example API
# ---------------------------------------------------------------------
@app.post("/example")
def example():
    data = request.json
    passages = data.get('passages', [])
    question = data.get('question', '')
    essay = data.get('essay', '')
    retry = data.get('retryConfirmed', False)

    try:
        char_base = int(data.get('charBase')) if data.get('charBase') else 600
        char_range = int(data.get('charRange')) if data.get('charRange') else 100
    except:
        char_base = 600
        char_range = 100

    min_chars = char_base - char_range
    max_chars = char_base + char_range
    if retry:
        min_chars += 100

    initial_prompt = f"""
아래는 학생이 작성한 논술문입니다. 이 글을 바탕으로 다음 작업을 수행해 주십시오.

1. 학생의 논술문을 기반으로, 평가 기준을 고려하여 예시답안을 작성하십시오.
- 문체는 고등학교 논술 평가에 적합하게 단정하고 객관적인 서술을 유지하십시오.
- 예시답안은 반드시 제시문에 포함된 정보와 주장 흐름만으로 구성하십시오.
- 제시문 정보를 해석·조합하여 논지를 전개해야 합니다.
- ❗ 제시문 밖의 배경지식, 상식, 사례, 정의 등을 활용하면 오답으로 간주합니다.
- 모든 주장과 근거는 반드시 제시문에서만 취해야 합니다.
- 예시답안 서두에 질문에 대한 명확한 답변을 반드시 제시하십시오.
- 글자 수는 학생이 작성한 논술문 기준({char_base} ± {char_range}자) 내에서 작성하십시오.

2. 예시답안과 학생의 논술문을 비교하여 분석하십시오. 각 항목별로 다음을 포함하십시오:
- 학생의 미흡한 문장 (직접 인용)
- 어떤 평가 기준에서 부족했는가
- 예시답안에서 어떻게 개선되었는가

3. 반드시 아래 JSON 형식으로만 출력하십시오. 설명 문구를 붙이지 마십시오.

{{
  "example": "예시답안을 여기에 작성하십시오.",
  "comparison": "비교 설명을 여기에 작성하십시오. 반드시 500~700자 분량."
}}

제시문:
{chr(10).join(passages)}

질문:
{question}

학생의 논술문:
{essay}
"""
    messages = [
        {"role": "system", "content":
         "너는 고등학생 논술 첨삭 선생님이다. "
         "예시답안과 비교설명 작성 시 제시문 밖의 배경지식/사실/사례 사용은 절대 금지다. "
         "이를 사용하면 무효로 간주된다. "
         "모든 주장과 근거는 반드시 입력된 제시문에서만 취한다. "
         "출력은 반드시 JSON만 사용한다."
        },
        {"role": "user", "content": initial_prompt}
    ]

    parsed = {}
    example_text = ""
    comparison_text = ""
    max_attempts = 2

    for attempt in range(max_attempts):
        try:
            res = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=messages,
                temperature=0.7,
                max_tokens=2000
            )
            content = res.choices[0].message.content
            print("🧾 GPT 응답 원문:\n", content)

            parsed = json.loads(content)
            new_example = parsed.get("example", "")
            new_comparison = parsed.get("comparison", "")

            length_ok = (len(new_example) >= min_chars and len(new_example) <= max_chars)

            if length_ok or attempt == max_attempts - 1:
                example_text = new_example
                comparison_text = new_comparison
                break

            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": (
                    f"방금 예시답안 길이 {len(new_example)}자입니다. "
                    f"반드시 {min_chars}자 이상 {max_chars}자 이하로, 제시문 내용만 활용하여 다시 작성하십시오."
                )
            })

        except json.JSONDecodeError:
            print("❌ JSON 파싱 실패:\n", content)
            continue
        except Exception as e:
            print("❗예외 발생 (example):", str(e), flush=True)
            return jsonify({"error": str(e)}), 500

    return jsonify({
        "example": example_text,
        "comparison": comparison_text,
        "length_valid": (len(example_text) >= min_chars and len(example_text) <= max_chars),
        "length_actual": len(example_text)
    })

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
