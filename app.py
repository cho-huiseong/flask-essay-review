from flask import Flask, request, jsonify, render_template
import openai

app = Flask(__name__)

openai.api_key = "your-openai-api-key"  # Render에선 환경변수로 설정 추천

@app.route('/')
def home():
    return render_template('index.html')  # HTML 폼 있는 페이지

@app.route('/review', methods=['POST'])  # ✅ 반드시 POST 포함!
def review_essay():
    data = request.get_json()
    essay = data.get("essay", "")

    prompt = (
        f"다음 논술문을 GPT-4 Turbo 기준으로 첨삭해주세요. "
        f"비판적 사고, 창의성, 논리성, 설득력 등을 기준으로 평가해 주세요:\n\n{essay}"
    )

    response = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "당신은 글쓰기 평가 전문가입니다."},
            {"role": "user", "content": prompt}
        ]
    )

    feedback = response.choices[0].message.content.strip()
    return jsonify({"feedback": feedback})

if __name__ == '__main__':
    app.run(debug=True)
