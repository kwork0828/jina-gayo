"""
jina-gayo : API 활용 국내 여행지 추천 프로그램
A1-2 과제 — 현재 단계: CLI 뼈대 + 1차 추천(Gemini)
"""

import argparse
import json
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

# ── 설정값 ──────────────────────────────────────────────
GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/{GEMINI_MODEL}:generateContent"
)
TIMEOUT = 60               # 초. 이 시간이 지나면 응답을 포기한다.
MAX_RETRY = 1              # 재시도는 최대 1회 (요건: 무한 재시도 금지)
MAX_OUTPUT_TOKENS = 8192   # '생각 + 답변'의 합계 한도


# ── 공통 도구 ───────────────────────────────────────────
def validate_date(date_text):
    """날짜 형식(YYYY-MM-DD)과 실제 존재하는 날짜인지를 함께 확인한다."""
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def parse_args():
    """터미널에서 입력한 옵션을 읽고 검증한다."""
    parser = argparse.ArgumentParser(
        prog="travel_planner.py",
        description="여행 날짜를 입력하면 국내 여행지를 추천하고 리포트를 만듭니다.",
    )
    parser.add_argument(
        "--date",
        "-date",
        required=True,
        metavar="YYYY-MM-DD",
        help="여행 날짜 (예: 2026-03-15)",
    )
    args = parser.parse_args()

    if not validate_date(args.date):
        parser.error(
            f"날짜 형식이 올바르지 않습니다: {args.date}  "
            f"→ YYYY-MM-DD 형식으로 입력해 주세요. (예: 2026-03-15)"
        )

    return args


def load_api_keys():
    """환경변수에서 API 키 2개를 읽는다. 하나라도 없으면 안내 후 즉시 종료한다."""
    gemini_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    kakao_key = (os.getenv("KAKAO_REST_API_KEY") or "").strip()

    missing = []
    if not gemini_key:
        missing.append("GEMINI_API_KEY")
    if not kakao_key:
        missing.append("KAKAO_REST_API_KEY")

    if missing:
        print("[오류] API 키가 설정되지 않았습니다:", ", ".join(missing))
        print()
        print("설정 방법 (둘 중 하나)")
        print("  1) GitHub Codespaces Secrets 에 등록한 뒤 Codespace를 재시작")
        print("  2) 프로젝트 폴더에 .env 파일을 만들고 아래처럼 입력")
        print("     GEMINI_API_KEY=여기에 본인 키")
        print("     KAKAO_REST_API_KEY=여기에 본인 키")
        print()
        print("  견본 파일이 있습니다:  cp .env.example .env")
        sys.exit(1)

    return gemini_key, kakao_key


def add_error(errors, step, err_type, message):
    """오류를 기록만 하고 프로그램은 계속 진행시킨다."""
    errors.append({"step": step, "type": err_type, "message": message})


def extract_json(text):
    """LLM 응답에서 첫 번째 JSON 객체를 잘라낸다. 끝이 잘렸으면 닫아서 복구한다."""
    cleaned = text.strip()

    # ```json ... ``` 코드블록이 섞여 있으면 { 가 들어 있는 조각만 남긴다.
    if "```" in cleaned:
        for chunk in cleaned.split("```"):
            if "{" in chunk:
                cleaned = chunk.strip()
                break
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]

    start = cleaned.find("{")
    if start == -1:
        raise ValueError("응답에서 JSON을 찾지 못했습니다.")

    # 괄호의 짝을 세면서 첫 번째 JSON이 끝나는 지점을 찾는다.
    # 문자열 안의 괄호와 이스케이프된 따옴표는 건너뛴다.
    stack = []
    in_string = False
    escaped = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
            if not stack:
                return json.loads(cleaned[start:i + 1])

    # 여기까지 왔다면 응답이 중간에 끊긴 것이다.
    # 열려 있는 괄호를 닫아서 살려본다 (부분 응답 복구).
    tail = cleaned[start:]
    if in_string:
        tail += '"'
    else:
        tail = tail.rstrip()
        if tail.endswith(","):
            tail = tail[:-1]
    for ch in reversed(stack):
        tail += "}" if ch == "{" else "]"
    return json.loads(tail)


# ── 1단계: LLM 1차 추천 ─────────────────────────────────
def call_gemini(prompt, api_key):
    """Gemini에 프롬프트를 보내고(POST) 생성된 텍스트를 돌려받는다."""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
        },
    }
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }

    response = requests.post(
        GEMINI_URL, headers=headers, json=payload, timeout=TIMEOUT
    )

    if response.status_code != 200:
        # 응답 본문에는 키가 들어가지 않으므로 그대로 보여줘도 안전하다.
        raise RuntimeError(f"HTTP {response.status_code} / {response.text[:300]}")

    data = response.json()
    candidate = data["candidates"][0]

    # STOP 이 아니면 답변이 중간에 끊긴 것이다.
    finish = candidate.get("finishReason")
    if finish and finish != "STOP":
        raise RuntimeError(f"답변이 끝까지 오지 않았습니다 (finishReason={finish})")

    parts = candidate.get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def build_prompt(date_text, strict=False):
    """1차 추천용 프롬프트를 만든다. strict=True 면 재시도용 최소 프롬프트."""
    if strict:
        return (
            f"{date_text} 국내 여행 추천. 설명 없이 JSON만 출력.\n"
            '{"recommended_city":"","weather":"","events":[],"reason":""}'
        )

    return (
        f"{date_text}에 대한민국 국내 여행하기 좋은 도시 한 곳을 추천하세요.\n"
        "설명 문장이나 코드블록 표시 없이, 아래 4개 키만 담은 JSON 하나만 출력하세요.\n"
        "각 값은 짧게 쓰세요. weather 는 한 문장, reason 은 두 문장 이내입니다.\n"
        '{"recommended_city": "도시명", '
        '"weather": "그 시기의 일반적인 날씨 한 문장", '
        '"events": ["행사나 축제 1~3개"], '
        '"reason": "추천 이유 두 문장 이내"}'
    )


def get_recommendation(date_text, api_key, errors):
    """1차 추천 JSON을 받아온다. 실패 시 1회만 재시도한다."""
    for attempt in range(MAX_RETRY + 1):
        strict = attempt > 0
        if strict:
            print("    - 재시도합니다(1회).")

        try:
            text = call_gemini(build_prompt(date_text, strict), api_key)
        except RuntimeError as e:
            # 우리가 직접 만든 오류라서 키가 섞일 일이 없다. 그대로 출력한다.
            add_error(errors, "llm_recommend", "API_ERROR", str(e))
            print("    - 호출 실패:", e)
            continue
        except Exception as e:
            # 그 외 오류는 종류만 출력한다 (키 노출 방지).
            add_error(errors, "llm_recommend", "API_ERROR", type(e).__name__)
            print("    - 호출 실패:", type(e).__name__)
            continue

        try:
            result = extract_json(text)
        except Exception as e:
            add_error(errors, "llm_recommend", "PARSE_ERROR", f"{type(e).__name__}: {e}")
            print(f"    - 파싱 실패: {type(e).__name__} - {e}")
            print(f"      응답 글자수 {len(text)} / 뒤 80자: {text[-80:]}")
            continue

        # 필수 키가 빠졌으면 채워 넣는다.
        result.setdefault("recommended_city", "서울")
        result.setdefault("weather", "정보 없음")
        result.setdefault("events", [])
        result.setdefault("reason", "정보 없음")
        return result

    # 재시도까지 모두 실패한 경우
    add_error(errors, "llm_recommend", "RETRY_FAILED", "재시도 1회도 실패")
    return {
        "recommended_city": "서울",
        "weather": "정보 없음",
        "events": [],
        "reason": "LLM 응답을 해석하지 못해 기본값을 사용했습니다.",
    }


# ── 전체 흐름 ───────────────────────────────────────────
def main():
    args = parse_args()
    gemini_key, kakao_key = load_api_keys()
    errors = []

    print(f"여행 날짜: {args.date}")
    print("[1/3] 1차 추천 생성 중(LLM)...")

    rec = get_recommendation(args.date, gemini_key, errors)

    print(f"    - recommended_city : {rec['recommended_city']}")
    print(f"    - weather          : {rec['weather']}")
    print(f"    - events           : {rec['events']}")
    print(f"    - reason           : {rec['reason'][:60]}...")
    print()
    print(f"오류 기록 {len(errors)}건: {errors}")


if __name__ == "__main__":
    main()

    