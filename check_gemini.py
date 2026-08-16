"""
Gemini 응답 원문을 파일로 저장해서 어디가 깨지는지 직접 확인한다.
"""

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
HEADERS = {"x-goog-api-key": KEY, "Content-Type": "application/json"}
URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-3.5-flash:generateContent"
)

PROMPT = (
    "2026-03-15에 대한민국 국내 여행하기 좋은 도시 한 곳을 추천하세요.\n"
    "설명 문장이나 코드블록 표시 없이, 아래 4개 키만 담은 JSON 하나만 출력하세요.\n"
    '{"recommended_city": "도시명", '
    '"weather": "그 시기의 일반적인 날씨 한 문장", '
    '"events": ["행사나 축제 1~3개"], '
    '"reason": "추천 이유 2~4문장"}'
)

payload = {
    "contents": [{"parts": [{"text": PROMPT}]}],
    "generationConfig": {
        "responseMimeType": "application/json",
        "maxOutputTokens": 8192,
    },
}

r = requests.post(URL, headers=HEADERS, json=payload, timeout=60)
print("상태 코드:", r.status_code)

data = r.json()

# 응답 전체를 파일로 남긴다 (키는 들어가지 않는다).
with open("raw_response.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("원문을 raw_response.json 에 저장했습니다.")
print()

candidate = data["candidates"][0]
print("finishReason :", candidate.get("finishReason"))

parts = candidate.get("content", {}).get("parts", [])
print("parts 개수   :", len(parts))
for i, p in enumerate(parts):
    print(f"  part{i} 키={list(p.keys())} 글자수={len(p.get('text', ''))}")

text = "".join(p.get("text", "") for p in parts)
print("이어붙인 전체 글자수:", len(text))
print()
print("--- 앞 120자 ---")
print(text[:120])
print()
print("--- 뒤 120자 ---")
print(text[-120:])
print()

# 실제로 파싱해 본다.
try:
    parsed = json.loads(text)
    print("[성공] JSON 파싱 OK. 키:", list(parsed.keys()))
except Exception as e:
    print("[실패]", type(e).__name__, "-", e)

    