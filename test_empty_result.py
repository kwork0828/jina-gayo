"""
맛집 검색 결과가 0건일 때 프로그램이 멈추지 않는지 확인한다.
실제로 존재하지 않는 지역명을 넣어 EMPTY_RESULT 경로를 시험한다.
"""

import os

from dotenv import load_dotenv

from travel_planner import search_restaurants

load_dotenv()

KEY = (os.getenv("KAKAO_REST_API_KEY") or "").strip()
errors = []

print("[테스트] 존재하지 않는 지역으로 맛집 검색")
places = search_restaurants("zzqqxx없는지역명", KEY, errors)

print()
print("반환된 맛집 수 :", len(places))
print("기록된 오류    :", errors)
print()
if len(places) == 0 and errors and errors[0]["type"] == "EMPTY_RESULT":
    print("[통과] 0건이어도 예외를 던지지 않고 빈 목록과 오류 기록을 돌려줍니다.")
else:
    print("[확인 필요] 예상과 다른 결과입니다.")
    