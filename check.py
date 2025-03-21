import openai
import os

# 🔹 환경 변수에서 API 키 가져오기
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# 사용 가능한 모델 목록 조회
try:
    models = client.models.list()

    print("✅ 사용 가능한 모델 목록:")
    for model in models.data:
        print(f"- {model.id}")

except Exception as e:
    print(f"❌ [ERROR] 모델 조회 실패: {str(e)}")
