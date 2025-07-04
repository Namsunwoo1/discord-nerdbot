import os
from dotenv import load_dotenv

print("🚀 .env 파일 로딩 중...")
load_dotenv()

token = os.getenv("DISCORD_TOKEN")

if token:
    print("✅ 토큰 정상 로드됨:")
    print(token[:20] + "..." + token[-10:])  # 일부만 출력
else:
    print("❌ 토큰을 .env에서 못 불러왔습니다.")
