# jina-gayo

여행 날짜 하나만 입력하면, AI가 갈 만한 도시를 골라주고 그 지역 맛집까지 찾아
**여행 리포트를 만들어 주는 CLI 프로그램**입니다.

> 이름의 뜻: "지나, 가요?" — 날짜를 던지면 어디로 갈지 답해줍니다.

---

## 어떻게 동작하나요

```
python travel_planner.py --date 2026-03-15
        |
        +- [1/3] Gemini API      : 그 시기에 좋은 도시 · 날씨 · 행사를 JSON으로 추천
        |                           |  recommended_city
        +- [2/3] Kakao Local API  : 그 도시의 맛집 5곳 검색
        |                           |
        +- [3/3] Gemini API       : 위 자료로 최종 여행 리포트(Markdown) 작성
        |
        +- results/ 폴더에 원본 JSON + 리포트 저장
```

**핵심은 AI의 답을 JSON으로 받아 다음 API의 검색어로 넘긴다는 점입니다.**
자유로운 문장이 아니라 정해진 형식으로 받기 때문에 프로그램이 값을 꺼내 쓸 수 있습니다.

---

## 준비물

| 항목 | 내용 |
|---|---|
| Python | 3.10 이상 |
| API 키 | Google Gemini, Kakao REST API — **둘 다 무료** |

### API 키 발급

| 키 이름 | 발급처 | 비고 |
|---|---|---|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com) | 구글 계정만 있으면 됨, 카드 등록 불필요 |
| `KAKAO_REST_API_KEY` | [Kakao Developers](https://developers.kakao.com) | 앱 생성 후 **REST API 키** 복사 |

> 카카오는 앱 화면에서 **카카오맵(지도/로컬) 서비스를 활성화**해야 합니다.
> 켜지 않으면 `403 NotAuthorizedError` 가 납니다.

---

## 설치

```
git clone https://github.com/kwork0828/jina-gayo.git
cd jina-gayo
pip install -r requirements.txt
```

---

## API 키 설정

**아래 세 가지 중 편한 방법 하나만** 하시면 됩니다.

### 방법 A — `.env` 파일 (가장 일반적)

견본 파일을 복사한 뒤 본인 키를 채웁니다.

```
cp .env.example .env
```

`.env` 파일을 열어 아래처럼 입력합니다.

```
GEMINI_API_KEY=여기에 본인 키
KAKAO_REST_API_KEY=여기에 본인 키
```

### 방법 B — 환경변수 (한 번만 쓸 때)

macOS / Linux

```
export GEMINI_API_KEY="여기에 본인 키"
export KAKAO_REST_API_KEY="여기에 본인 키"
```

Windows PowerShell

```
$env:GEMINI_API_KEY="여기에 본인 키"
$env:KAKAO_REST_API_KEY="여기에 본인 키"
```

### 방법 C — GitHub Codespaces Secrets (이 프로젝트의 개발 환경)

`github.com/settings/codespaces` 에서 `New secret` 을 눌러 위 두 이름으로 등록하면,
Codespace가 켜질 때 환경변수로 자동 주입됩니다. **키를 파일로 들고 다니지 않아도 됩니다.**

> 키가 하나라도 없으면 프로그램은 **즉시 종료하며 설정 방법을 안내**합니다.

---

## 실행 방법

```
python travel_planner.py --date 2026-03-15
```

| 옵션 | 설명 |
|---|---|
| `--date YYYY-MM-DD` | **필수.** 여행 날짜. 형식이 틀리면 사용법을 보여주고 종료합니다 |
| `--refresh` | 저장된 결과를 무시하고 API를 다시 호출합니다 |
| `--help` | 사용법 보기 |

### 실행 화면

```
여행 날짜: 2026-03-15
[1/3] 1차 추천 생성 중(LLM)...
    - recommended_city : 경주
[2/3] 맛집 검색 중(지도/장소 API)...
    - 맛집 5곳 검색 완료
[3/3] 최종 리포트 생성 중(LLM)...
    - 리포트 생성 완료

완료! results/2026-03-15_travel_plan.md 를 확인하세요.
```

### 같은 날짜로 다시 실행하면

이미 저장된 결과가 있으면 **API를 호출하지 않고** 그 자료로 리포트를 다시 만듭니다.

```
[캐시] 저장된 결과를 찾았습니다. API 호출 2회를 건너뜁니다.
```

새로 받고 싶으면 `--refresh` 를 붙이세요.

---

## 결과물 확인

실행이 끝나면 `results/` 폴더에 파일 두 개가 생깁니다.

```
results/
├── 2026-03-15_raw.json        원본 데이터
└── 2026-03-15_travel_plan.md  최종 여행 리포트
```

### `_travel_plan.md` — 사람이 읽는 리포트

VS Code에서 파일을 열고 `Ctrl+Shift+V` 를 누르면 보기 좋게 표시됩니다.
아래 절이 들어 있습니다.

```
## 추천 지역        ## 추천 이유      ## 날씨 요약
## 행사/축제        ## 맛집 추천      ## 1일 일정 제안
## 오류 요약(errors)
```

### `_raw.json` — 프로그램이 받은 원본 데이터

```json
{
  "date": "2026-03-15",
  "generated_at": "2026-08-16T12:00:00",
  "recommendation": {
    "recommended_city": "경주",
    "weather": "...",
    "events": ["..."],
    "reason": "..."
  },
  "restaurants": [
    {
      "name": "...",
      "address": "...",
      "category": "...",
      "url": "...",
      "x": 129.21,
      "y": 35.83
    }
  ],
  "errors": []
}
```

---

## API 키 관리 — 반드시 읽어주세요

**API 키는 비밀번호와 같습니다.** 유출되면 남이 내 이름으로 API를 쓰고, 요금이 청구될 수 있습니다.

이 프로젝트는 다음을 지킵니다.

- 코드에 키를 직접 쓰지 않습니다. `os.getenv()` 로만 읽습니다
- `.gitignore` 에 `.env` 가 등록되어 있어 **커밋되지 않습니다**
- 저장소에는 키가 없는 견본 `.env.example` 만 올라갑니다
- 화면·로그·결과 파일에 키를 출력하지 않습니다

### 사용하실 때 주의할 점

| 하지 마세요 | 이유 |
|---|---|
| `.gitignore` 에서 `.env` 를 지우기 | 다음 커밋에 키가 그대로 올라갑니다 |
| 키가 보이는 화면을 캡처해 올리기 | 이미지도 유출 경로입니다 |
| 오류 메시지를 그대로 복사해 공개하기 | **오류 로그에 키가 섞여 나올 수 있습니다** |

> 키가 노출됐다면 **즉시 폐기하고 새로 발급**하세요. 두 서비스 모두 몇 초면 됩니다.

---

## 자주 나는 오류

| 화면 | 원인 | 해결 |
|---|---|---|
| `API 키가 설정되지 않았습니다` | 키 미설정 | 위 "API 키 설정" 참고 |
| Kakao `401` | 키가 틀림 | **REST API 키**가 맞는지 확인 |
| Kakao `403` | 권한 없음 | 카카오 콘솔에서 **카카오맵 활성화** |
| Gemini `429` | 무료 한도 초과 | 잠시 뒤 재시도, 또는 캐시 사용 |
| Gemini `404` | 모델 이름 문제 | `travel_planner.py` 의 `GEMINI_MODEL` 값 수정 |

**어떤 오류가 나도 프로그램은 멈추지 않습니다.** 실패한 단계는 `errors` 에 기록되고
리포트의 `오류 요약` 절에 남으며, 리포트 자체는 반드시 생성됩니다.

---

## 파일 구성

```
jina-gayo/
├── travel_planner.py       메인 프로그램
├── test_empty_result.py    검색 0건 상황 확인용 테스트
├── requirements.txt        필요한 라이브러리 목록
├── .env.example            키 견본 (실제 키 없음)
├── README.md               이 문서
├── report.md               과제 수행 보고서
├── images/                 보고서용 화면 캡처
└── results/                실행 결과 (자동 생성)
```

---

## 사용한 기술

| 구분 | 내용 |
|---|---|
| 언어 | Python 3.12 |
| LLM API | Google Gemini |
| 지도/장소 API | Kakao Local — 키워드 장소 검색 |
| 라이브러리 | `requests`, `python-dotenv` |
| 개발 환경 | GitHub Codespaces (Ubuntu / bash) |
