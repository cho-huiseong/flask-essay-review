from flask import Flask, request, jsonify, render_template, make_response
from flask_cors import CORS
from openai import OpenAI
import os, json
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
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
CORS(app, supports_credentials=True)

# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

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
        return db.query(User).get(int(user_id))
    finally:
        db.close()

def _normalize_email(s):
    return (s or "").strip().lower()

# ---------------------------------------------------------------------
# Admin seed (선택, 스키마 변경 없음)
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
        return jsonify({"ok": True, "user": {"id": user.id, "email": user.email, "name": user.name, "is_admin": _is_admin(user)}})
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

# ---------- AI: Review ----------
def _fallback_scores_and_reasons():
    # OpenAI 키가 없을 때도 동작(데모)
    return [8, 7, 7, 8], {
        "논리력": "주장을 제시하고 근거로 뒷받침했어요.",
        "독해력": "제시문 핵심을 대체로 반영했어요.",
        "구성력": "문단 전환과 연결이 자연스러워요.",
        "표현력": "문법 오류가 거의 없고 어휘가 적절합니다."
    }

@app.post("/review")
@login_required
def review():
    data = request.get_json(force=True)
    # name 또는 student 둘 다 수용
    student = (data.get("student") or data.get("name") or "").strip()
    question = (data.get("question") or "").strip()
    passages = data.get("passages") or []
    essay = (data.get("essay") or "").strip()

    try:
        if client:
            prompt = f"""
당신은 한국어 논술 평가 교사입니다.
기준: 논리력/독해력/구성력/표현력 각 0~10점.
입력 제시문: {passages}
질문: {question}
학생 글: {essay}
출력은 JSON(object)으로:
{{
  "scores": [논리력,독해력,구성력,표현력],
  "reasons": {{
    "논리력":"...","독해력":"...","구성력":"...","표현력":"..."
  }}
}}
            """.strip()
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"system","content":"Output must be valid JSON."},
                          {"role":"user","content":prompt}],
                temperature=0.2
            )
            content = resp.choices[0].message.content
            data = json.loads(content)
            scores = data.get("scores") or [0,0,0,0]
            reasons = data.get("reasons") or {}
        else:
            scores, reasons = _fallback_scores_and_reasons()

        return jsonify({"scores": scores, "reasons": reasons})
    except Exception as e:
        print("❗ review error:", e, flush=True)
        return jsonify({"error": str(e)}), 500

# ---------- AI: Example ----------
@app.post("/example")
@login_required
def example():
    data = request.get_json(force=True)
    student = (data.get("student") or data.get("name") or "").strip()
    question = (data.get("question") or "").strip()
    passages = data.get("passages") or []
    essay = (data.get("essay") or "").strip()
    char_base = int(data.get("charBase") or 0)
    char_range = int(data.get("charRange") or 0)
    min_chars = max(0, char_base - char_range)
    max_chars = char_base + char_range

    try:
        if client:
            prompt = f"""
너는 한국어 논술 교사다.
아래 학생 글의 말투를 유지하되, 제시문 기반으로 더 논리정연한 예시답안을 한 편 작성하라.
그리고 기존 글과 예시답안을 비교하여 개선 포인트를 3~5개 bullet로 요약하라.
반환은 JSON(object):
{{
  "example": "예시답안",
  "comparison": "비교 분석"
}}
제약: 글자수 권장 범위는 {min_chars}~{max_chars}자 (권장일 뿐 초과/미만이어도 출력).
입력 제시문: {passages}
질문: {question}
학생 글: {essay}
            """.strip()
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"system","content":"Output must be valid JSON."},
                          {"role":"user","content":prompt}],
                temperature=0.3
            )
            content = resp.choices[0].message.content
            parsed = json.loads(content)
            example_text = (parsed.get("example") or "").strip()
            comparison_text = (parsed.get("comparison") or "").strip()
        else:
            example_text = "예시답안(데모): 제시문 논지를 바탕으로 핵심을 압축해 전개합니다..."
            comparison_text = "- 논리의 흐름이 매끄럽도록 주장과 근거를 인접 배치\n- 제시문 문장 인용은 요약 위주로…"

        return jsonify({
            "example": example_text,
            "comparison": comparison_text,
            "length_valid": (len(example_text) >= min_chars and len(example_text) <= max_chars) if char_base else True,
            "length_actual": len(example_text)
        })
    except Exception as e:
        print("❗ example error:", e, flush=True)
        return jsonify({"error": str(e)}), 500

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
