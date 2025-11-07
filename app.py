from flask import Flask, request, jsonify, render_template, make_response
from flask_cors import CORS
from openai import OpenAI
import os, json, re  # ← re 추가
from datetime import datetime

# ==== Auth/DB ====
from flask_login import (
    LoginManager, login_user, logout_user, login_required,
    current_user, UserMixin
)
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

# 🔐 세션/쿠키 설정 (크로스 도메인에서 쿠키가 안 실리는 문제 해결)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-key"),
    SESSION_COOKIE_SAMESITE="Lax",   # 교차사이트 아니면 Lax가 안전/단순
    SESSION_COOKIE_SECURE=True,
    # SESSION_COOKIE_DOMAIN 설정하지 말 것(같은 도메인이라 불필요)
)


# 🌐 CORS: 와일드카드(*) 금지, 실제 프론트 주소를 명시
CORS(
    app,
    supports_credentials=True,
    resources={
        r"/*": {
            "origins": [
                "https://flask-essay-review.onrender.com"
            ]
        }
    },
)
# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ---------- JSON parse helper (safe) ----------
def parse_json_safely(s: str):
    try:
        return json.loads(s)
    except Exception:
        # 코드펜스/부가 문구 제거 후, 첫 번째 JSON 블록만 추출
        s2 = re.sub(r"^```json|^```|```$", "", s.strip(), flags=re.IGNORECASE|re.MULTILINE)
        m = re.search(r"\{.*\}", s2, flags=re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise

# ---------------------------------------------------------------------
# DB
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

    def set_password(self, raw: str):
        self.password_hash = bcrypt.hash(raw)

    def check_password(self, raw: str) -> bool:
        try:
            return bcrypt.verify(raw, self.password_hash)
        except Exception:
            return False

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True, index=True)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)

# ---------------------------------------------------------------------
# Login Manager
# ---------------------------------------------------------------------
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    db = SessionLocal()
    try:
        return db.query(User).get(int(user_id))  # SA 2.x 경고만 뜨는 구문(동작 OK)
    finally:
        db.close()

def _normalize_email(s):
    return (s or "").strip().lower()

# ---------------------------------------------------------------------
# 🔧 Utils
# ---------------------------------------------------------------------
def _s(v):
    """문자/None만 strip. 리스트/숫자 들어와도 안전하게 문자열로."""
    if isinstance(v, str):
        return v.strip()
    return "" if v is None else str(v)

def _coerce_passages(raw):
    """제시문이 문자열/배열 어떤 형태로 와도 문자열 리스트로 통일."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, str)]
    return [str(raw)]

CRITERIA_KEYS = ["논리력","독해력","구성력","표현력"]

def parse_review_text(block: str):
    """[항목] 점수: N / 이유: ... 형식의 텍스트에서 점수·이유를 추출"""
    scores = []
    reasons = {}
    for key in CRITERIA_KEYS:
        pat = rf"\[{key}\][\s\S]*?점수\s*:\s*(\d+)[\s\S]*?이유\s*:\s*(.+?)(?=\n\s*\[|$)"
        m = re.search(pat, block, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if m:
            score = max(0, min(10, int(m.group(1))))
            reason = m.group(2).strip()
        else:
            score, reason = 0, ""
        scores.append(score)
        reasons[key] = reason
    return scores, reasons


# ---------------------------------------------------------------------
# Admin seed (선택)
# ---------------------------------------------------------------------
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme!")
ADMIN_NAME = os.environ.get("ADMIN_NAME", "Admin")

if ADMIN_EMAIL:
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(email=_normalize_email(ADMIN_EMAIL)).first():
            u = User(email=_normalize_email(ADMIN_EMAIL), name=ADMIN_NAME)
            u.set_password(ADMIN_PASSWORD)
            db.add(u)
            db.commit()
            print(f"✅ Seeded admin: {ADMIN_EMAIL}", flush=True)
    finally:
        db.close()

def _is_admin(user: User) -> bool:
    return bool(ADMIN_EMAIL and user and _normalize_email(user.email) == _normalize_email(ADMIN_EMAIL))

# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/")
def index():
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-store"
    return resp

# ---------- Auth ----------
@app.post("/auth/register")
def auth_register():
    data = request.get_json(force=True)
    email = _normalize_email(data.get("email"))
    password = _s(data.get("password"))
    name = _s(data.get("name"))

    if not email or not password or not name:
        return jsonify({"ok": False, "error": "필수 정보가 누락되었습니다."}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "error": "비밀번호는 6자 이상이어야 합니다."}), 400
    if len(password.encode("utf-8")) > 72:
        return jsonify({"ok": False, "error": "비밀번호는 [영문 72자, 한글 약 24자] 이하로 설정해 주세요."}), 400

    db = SessionLocal()
    try:
        if db.query(User).filter_by(email=email).first():
            return jsonify({"ok": False, "error": "이미 가입된 이메일입니다."}), 400
        user = User(email=email, name=name)
        user.set_password(password)
        db.add(user)
        db.commit()
        login_user(user, remember=True)
        return jsonify({"ok": True, "user": {"id": user.id, "email": user.email, "name": user.name, "is_admin": _is_admin(user)}})
    finally:
        db.close()

@app.post("/auth/login")
def auth_login():
    data = request.get_json(force=True)
    email = _normalize_email(data.get("email"))
    password = _s(data.get("password"))

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        if not user or not user.check_password(password):
            return jsonify({"ok": False, "error": "이메일 또는 비밀번호가 올바르지 않습니다."}), 401
        login_user(user, remember=True)
        return jsonify({"ok": True, "user": {"id": user.id, "email": user.email, "name": user.name, "is_admin": _is_admin(user)}})
    finally:
        db.close()

@app.post("/auth/logout")
def auth_logout():
    logout_user()
    return jsonify({"ok": True})

@app.get("/auth/me")
def auth_me():
    if not current_user.is_authenticated:
        return jsonify({"ok": True, "user": None})
    return jsonify({"ok": True, "user": {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "is_admin": _is_admin(current_user)
    }})
# ---------- Response Header Sanitizer (skip Set-Cookie) ----------
@app.after_request
def _sanitize_headers(resp):
    """
    - Set-Cookie는 그대로 보존 (속성 깨짐 방지)
    - 그 외 헤더만 개행 제거 + latin-1 안전화
    - Duplicate headers 보존
    """
    try:
        pairs = resp.headers.to_wsgi_list()  # [('Header','...'), ('Set-Cookie','...'), ...]
        resp.headers.clear()
        for k, v in pairs:
            if k.lower() == "set-cookie":
                # 쿠키 헤더는 원본 그대로 재추가 (속성과 인코딩 건드리지 않음)
                resp.headers.add(k, v)
                continue
            sv = str(v).replace("\r", "").replace("\n", " ")
            try:
                sv.encode("latin-1", "strict")
            except UnicodeEncodeError:
                sv = sv.encode("latin-1", "ignore").decode("latin-1")
            resp.headers.add(k, sv)
        resp.headers.setdefault("Vary", "Origin")
    except Exception:
        pass
    return resp
# ------------------------------------------------------------------

# ---------- AI: Review ----------
@app.post("/review")
@login_required
def review():
    data = request.get_json(force=True)
    student = _s(data.get("student") or data.get("name"))
    question = _s(data.get("question"))
    essay = _s(data.get("essay"))
    passages = _coerce_passages(data.get("passages"))

    try:
        if client:
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
{passages}

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

[총평]
한 줄(40~90자)로 전체 인상을 요약하세요. 가장 미흡한 항목을 중심으로 구체적으로 적되, 1문장만 작성하세요.

            """.strip()

            resp = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": "너는 초등 논술 첨삭 선생님이야. 평가 기준에 따라 평가만 작성해."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500
            )

            content = resp.choices[0].message.content or ""
            summary = ""  # ⬅ 요약 변수 준비
            print("🧾 REVIEW 원문:\n", content)  # (선택) 로그 확인용

            # 1) 혹시 JSON으로 올 때 먼저 시도
            try:
                data_json = parse_json_safely(content)
                scores = data_json.get("scores") or [0,0,0,0]
                reasons = data_json.get("reasons") or {}
                summary = _s(data_json.get("summary"))  # ⬅ JSON이면 summary 키에서
            except Exception:
                # 2) 현재 프롬프트의 텍스트 형식([논리력]… 점수/이유) 파싱
                scores, reasons = parse_review_text(content)
                # ⬅ 텍스트에선 [총평] 블록에서 한 줄 추출
                m = re.search(r"\[총평\]\s*(.+)", content, flags=re.IGNORECASE|re.DOTALL)
                summary = _s(m.group(1)) if m else ""

        else:
            # OpenAI 키 없을 때 폴백
            scores = [8,7,7,8]
            reasons = {
                "논리력":"주장을 제시하고 근거로 뒷받침했어요.",
                "독해력":"제시문 핵심을 대체로 반영했어요.",
                "구성력":"문단 전환과 연결이 자연스러워요.",
                "표현력":"문법 오류가 거의 없고 어휘가 적절합니다."
            }
            summary = "전체적으로 안정적이지만, 제시문 근거를 더 명시하며 논리 전개를 강화해 보세요."
        return jsonify({"scores": scores, "reasons": reasons, "summary": summary})

    except Exception as e:
        print("❗예외 발생 (review):", str(e), flush=True)
        return jsonify({"error": str(e)}), 500


# ---------- AI: Example ----------
@app.post("/example")
def example():
    data = request.json or {}
    passages = _coerce_passages(data.get('passages'))
    question = _s(data.get('question'))
    essay = _s(data.get('essay'))
    retry = bool(data.get('retryConfirmed'))

    try:
        char_base = int(data.get('charBase')) if data.get('charBase') is not None else 600
        char_range = int(data.get('charRange')) if data.get('charRange') is not None else 100
    except Exception:
        char_base = 600
    # 위 except에서 char_range가 안 잡힐 수 있으니 보정
    char_range = char_range if isinstance(char_range, int) else 100

    min_chars = max(0, char_base - char_range)
    max_chars = char_base + char_range
    if retry:
        min_chars += 100

    initial_prompt = f"""
아래는 학생이 작성한 논술문입니다. 이 글을 바탕으로 다음 작업을 수행해 주십시오.

1. 학생의 논술문을 기반으로, 평가 기준을 고려하여 예시답안을 작성하십시오.
- 문체는 고등학교 논술 평가에 적합하게 단정하고 객관적인 서술을 유지하십시오.
- 예시답안은 반드시 제시문에 포함된 정보와 주장 흐름만으로 구성하십시오.
- 제시문 정보를 해석·조합하여 논지를 전개해야 합니다.
- ❗ 제시문 밖의 배경지식, 상식, 사례, 정의 등을 활용하면 오답으로 간주합니다. (즉시 무효 처리)
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
""".strip()

    messages = [
        {"role": "system", "content":
         "너는 고등학생 논술 첨삭 선생님이다. "
         "예시답안과 비교설명 작성 시 제시문 밖의 배경지식/사실/사례 사용은 절대 금지다. "
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
                max_tokens=2000,
                response_format={"type": "json_object"}  # ← JSON 모드 강제
            )
            content = res.choices[0].message.content
            print("🧾 GPT 응답 원문:\n", content)

            parsed = parse_json_safely(content)  # ← 안전 파싱 적용
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
                    f"반드시 {min_chars}자 이상 {max_chars}자 이하로, 제시문 내용만 활용하여 다시 작성하십시오. "
                    f"배경지식/외부 정보를 사용하면 무효입니다."
                )
            })

        except json.JSONDecodeError:
            print("❌ JSON 파싱 실패:\n", content)
            continue
        except Exception as e:
            print("❗예외 발생 (example):", str(e), flush=True)
            return jsonify({"error": str(e)}), 500

    # 길이 기준 안내 + 최종 폴백(빈 값 방지)
    length_valid = (len(example_text) >= min_chars and len(example_text) <= max_chars)
    length_note = "" if length_valid else (
        f"※ 본 예시는 권장 글자수 범위({min_chars}~{max_chars}자)와 "
        f"{abs(len(example_text) - char_base)}자 차이가 있습니다. 제시문 내에서 최대한 근접하게 생성했어요."
    )

    # 최종 폴백: 파싱이 끝까지 안 되었을 때라도 원문을 노출
    if not example_text and 'content' in locals() and content:
        example_text = content.strip()
        comparison_text = comparison_text or ""

    return jsonify({
        "example": example_text,
        "comparison": comparison_text,
        "length_valid": length_valid,
        "length_actual": len(example_text),
        "length_note": length_note  # (프런트에서 선택적으로 노출 가능)
    })

# ---------- Reports ----------
@app.post("/reports")
@login_required
def create_report():
    data = request.get_json(force=True)
    try:
        payload = json.dumps(data, ensure_ascii=False)
    except Exception:
        return jsonify({"ok": False, "error": "payload_json 직렬화 실패"}), 400

    db = SessionLocal()
    try:
        r = Report(user_id=current_user.id, payload_json=payload)
        db.add(r)
        db.commit()
        return jsonify({"ok": True, "id": r.id, "created_at": r.created_at.isoformat()})
    finally:
        db.close()

@app.get("/reports")
@login_required
def list_reports():
    db = SessionLocal()
    try:
        rows = (
            db.query(Report)
            .filter(Report.user_id == current_user.id)
            .order_by(Report.created_at.desc())
            .limit(50)
            .all()
        )
        items = []
        for r in rows:
            try:
                p = json.loads(r.payload_json)
            except Exception:
                p = {}
            items.append({
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "student": p.get("student") or p.get("name"),
                "total": p.get("total"),
                "status": p.get("status"),
                "title": (p.get("question") or "")[:40]
            })
        return jsonify({"ok": True, "items": items})
    finally:
        db.close()

@app.get("/reports/<int:rid>")
@login_required
def get_report(rid):
    db = SessionLocal()
    try:
        r = db.query(Report).filter_by(id=rid, user_id=current_user.id).first()
        if not r:
            return jsonify({"ok": False, "error": "존재하지 않거나 권한이 없습니다."}), 404
        return jsonify({"ok": True, "id": r.id, "created_at": r.created_at.isoformat(), "payload": json.loads(r.payload_json)})
    finally:
        db.close()

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
