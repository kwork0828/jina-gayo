"""
jina-gayo : API 활용 국내 여행지 추천 프로그램
A1-2 과제 — CLI + 1차 추천(Gemini) + 맛집 검색(Kakao) + 최종 리포트 저장
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# ── 설정값 ──────────────────────────────────────────────
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/{GEMINI_MODEL}:generateContent"
)
KAKAO_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

TIMEOUT = 60               # 초. 이 시간이 지나면 응답을 포기한다.
MAX_RETRY = 1              # 재시도는 최대 1회 (요건: 무한 재시도 금지)
MAX_OUTPUT_TOKENS = 8192   # '생각 + 답변'의 합계 한도
PLACE_COUNT = 5            # 맛집 검색 개수 (과제 권장 5곳)


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
def call_gemini(prompt, api_key, json_mode=True):
    """Gemini에 프롬프트를 보내고(POST) 생성된 텍스트를 돌려받는다."""
    config = {"maxOutputTokens": MAX_OUTPUT_TOKENS}
    if json_mode:
        # 1차 추천은 JSON으로 받아야 하고, 최종 리포트는 Markdown이라 끈다.
        config["responseMimeType"] = "application/json"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": config,
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


# ── 2단계: 지도/장소 API 맛집 검색 ──────────────────────
def to_float(value):
    """카카오는 좌표를 문자열로 준다. 숫자로 바꾸되 실패하면 None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def search_restaurants(city, api_key, errors):
    """추천 도시로 맛집을 검색한다. 실패해도 빈 리스트를 돌려주고 계속 진행한다."""
    query = f"{city} 맛집"
    headers = {"Authorization": f"KakaoAK {api_key}"}
    params = {"query": query, "size": PLACE_COUNT}

    try:
        # GET 요청: 검색어를 주소 뒤에 붙여서 보낸다.
        response = requests.get(
            KAKAO_URL, headers=headers, params=params, timeout=TIMEOUT
        )
    except Exception as e:
        add_error(errors, "place_search", "NETWORK_ERROR", type(e).__name__)
        print("    - 네트워크 오류:", type(e).__name__, "→ 맛집 없이 계속 진행합니다.")
        return []

    if response.status_code in (401, 403):
        add_error(errors, "place_search", "AUTH_ERROR", f"HTTP {response.status_code}")
        print(f"    - 오류: 인증 실패({response.status_code}). 키 설정을 확인하세요.")
        print("    - 맛집 섹션은 '데이터 없음'으로 처리하고 계속 진행합니다.")
        return []

    if response.status_code == 429:
        add_error(errors, "place_search", "QUOTA_ERROR", "HTTP 429")
        print("    - 오류: 호출 한도 초과(429) → 맛집 없이 계속 진행합니다.")
        return []

    if response.status_code != 200:
        add_error(errors, "place_search", "API_ERROR", f"HTTP {response.status_code}")
        print(f"    - 오류: HTTP {response.status_code} → 맛집 없이 계속 진행합니다.")
        return []

    documents = response.json().get("documents", [])
    if not documents:
        add_error(errors, "place_search", "EMPTY_RESULT", f"0 results for query={query}")
        print(f"    - 검색 결과 0건 (query={query}) → 데이터 없음으로 진행합니다.")
        return []

    # 카카오의 필드명을 우리 스키마 이름으로 바꿔 담는다.
    places = []
    for doc in documents:
        places.append(
            {
                "name": doc.get("place_name", ""),
                "address": doc.get("road_address_name") or doc.get("address_name", ""),
                "category": doc.get("category_name", ""),
                "url": doc.get("place_url", ""),
                "x": to_float(doc.get("x")),
                "y": to_float(doc.get("y")),
            }
        )

    print(f"    - 맛집 {len(places)}곳 검색 완료")
    return places


# ── 3단계: 최종 리포트 생성 ─────────────────────────────
def places_to_text(places):
    """맛집 목록을 프롬프트에 넣기 좋은 글로 바꾼다."""
    if not places:
        return "(데이터 없음)"
    lines = []
    for p in places:
        lines.append(f"- {p['name']} / {p['category']} / {p['address']} / {p['url']}")
    return "\n".join(lines)


def build_report_prompt(date_text, rec, places):
    """최종 리포트용 프롬프트를 만든다."""
    return (
        f"아래 자료로 {date_text} 국내 여행 리포트를 한국어 Markdown으로 작성하세요.\n"
        "코드블록 표시는 쓰지 말고 Markdown 본문만 출력하세요.\n"
        "자료에 없는 가게 이름이나 행사는 절대 지어내지 마세요.\n\n"
        f"제목은 '# {date_text} 국내 여행 추천 리포트' 로 시작하세요.\n"
        "아래 여섯 개 절을 반드시 넣으세요.\n"
        "## 추천 지역\n## 추천 이유\n## 날씨 요약\n## 행사/축제\n"
        "## 맛집 추천\n## 1일 일정 제안\n\n"
        "'맛집 추천'은 아래 목록만 표로 정리하세요. 목록이 '(데이터 없음)'이면 "
        "'- 데이터 없음 (장소 검색 결과 0건)' 한 줄만 쓰세요.\n"
        "'1일 일정 제안'은 오전/오후/저녁 세 줄로 쓰세요.\n\n"
        "### 자료\n"
        f"날짜: {date_text}\n"
        f"추천 도시: {rec['recommended_city']}\n"
        f"날씨: {rec['weather']}\n"
        f"행사: {rec['events']}\n"
        f"추천 이유: {rec['reason']}\n"
        f"맛집 목록:\n{places_to_text(places)}\n"
    )


def build_fallback_report(date_text, rec, places):
    """LLM 리포트 생성이 실패해도 리포트는 반드시 만든다(파이썬으로 직접 조립)."""
    lines = [f"# {date_text} 국내 여행 추천 리포트", ""]
    lines += ["## 추천 지역", "", f"- {rec['recommended_city']}", ""]
    lines += ["## 추천 이유", "", rec["reason"], ""]
    lines += ["## 날씨 요약", "", rec["weather"], ""]

    lines += ["## 행사/축제", ""]
    if rec["events"]:
        lines += [f"- {e}" for e in rec["events"]]
    else:
        lines.append("- 데이터 없음")
    lines.append("")

    lines += ["## 맛집 추천", ""]
    if places:
        lines.append("| 이름 | 분류 | 주소 |")
        lines.append("|---|---|---|")
        for p in places:
            lines.append(f"| {p['name']} | {p['category']} | {p['address']} |")
    else:
        lines.append("- 데이터 없음 (장소 검색 결과 0건)")
    lines.append("")

    lines += ["## 1일 일정 제안", ""]
    lines.append(f"- 오전: {rec['recommended_city']} 도착 후 주변 산책")
    if places:
        lines.append(f"- 오후: {places[0]['name']} 에서 점심 식사")
    else:
        lines.append("- 오후: 지역 명소 방문")
    lines.append("- 저녁: 숙소 주변 야경 감상")
    lines.append("")
    return "\n".join(lines)


def append_errors_section(markdown, errors):
    """오류 요약은 LLM이 지어내지 않도록 코드가 직접 붙인다."""
    lines = [markdown.rstrip(), "", "## 오류 요약(errors)", ""]
    if not errors:
        lines.append("- 없음")
    else:
        for e in errors:
            lines.append(f"- `{e['step']}` / `{e['type']}` : {e['message'][:120]}")
    lines.append("")
    return "\n".join(lines)


def generate_report(date_text, rec, places, api_key, errors):
    """최종 리포트를 Markdown으로 만든다. 실패하면 직접 조립한 리포트를 쓴다."""
    try:
        text = call_gemini(
            build_report_prompt(date_text, rec, places), api_key, json_mode=False
        )
        body = text.strip()
        if body.startswith("```"):
            body = body.split("```")[1]
            if body.startswith("markdown"):
                body = body[8:]
        if "#" not in body:
            raise ValueError("리포트 형식이 아닙니다.")
    except Exception as e:
        message = str(e) if isinstance(e, (RuntimeError, ValueError)) else type(e).__name__
        add_error(errors, "llm_report", "API_ERROR", message)
        print("    - 리포트 생성 실패 → 기본 리포트로 대체합니다:", message[:80])
        body = build_fallback_report(date_text, rec, places)

    return append_errors_section(body, errors)


# ── 결과 저장 ───────────────────────────────────────────
def save_results(date_text, payload, markdown):
    """results/ 폴더를 만들고 원본 JSON과 최종 리포트를 저장한다."""
    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)

    json_path = results_dir / f"{date_text}_raw.json"
    md_path = results_dir / f"{date_text}_travel_plan.md"

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


# ── 전체 흐름 ───────────────────────────────────────────
def main():
    args = parse_args()
    gemini_key, kakao_key = load_api_keys()
    errors = []

    print(f"여행 날짜: {args.date}")

    print("[1/3] 1차 추천 생성 중(LLM)...")
    rec = get_recommendation(args.date, gemini_key, errors)
    print(f"    - recommended_city : {rec['recommended_city']}")

    print("[2/3] 맛집 검색 중(지도/장소 API)...")
    places = search_restaurants(rec["recommended_city"], kakao_key, errors)

    print("[3/3] 최종 리포트 생성 중(LLM)...")
    markdown = generate_report(args.date, rec, places, gemini_key, errors)
    print("    - 리포트 생성 완료")

    payload = {
        "date": args.date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "recommendation": rec,
        "restaurants": places,
        "errors": errors,
    }
    json_path, md_path = save_results(args.date, payload, markdown)

    print()
    print(f"완료! {md_path} 를 확인하세요.")
    print(f"      원본 데이터는 {json_path} 에 있습니다.")
    print(f"      오류 기록 {len(errors)}건")


if __name__ == "__main__":
    main()
    