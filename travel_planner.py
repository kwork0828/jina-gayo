"""
jina-gayo : API 활용 국내 여행지 추천 프로그램
A1-2 과제 — 현재 단계: CLI 뼈대 (날짜 검증 + API 키 확인)
"""

import argparse
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# .env 파일이 있으면 읽어서 환경변수로 올린다.
# Codespaces Secrets를 쓰는 환경에서는 .env가 없어도 그냥 넘어간다.
load_dotenv()


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
    gemini_key = os.getenv("GEMINI_API_KEY")
    kakao_key = os.getenv("KAKAO_REST_API_KEY")

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


def main():
    args = parse_args()
    gemini_key, kakao_key = load_api_keys()

    print(f"[준비] 여행 날짜   : {args.date}")
    print(f"[준비] Gemini 키   : {len(gemini_key)}자 확인")
    print(f"[준비] Kakao  키   : {len(kakao_key)}자 확인")
    print("[준비] 다음 단계에서 실제 API를 호출합니다.")


if __name__ == "__main__":
    main()
    