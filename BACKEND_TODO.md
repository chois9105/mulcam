# 백엔드 담당 업무 정리 (노희선)

작성일: 2026-08-25 · 저장소: chois9105/mulcam

---

## 팀 현황

| 담당 | 작업물 | 상태 |
|---|---|---|
| chois9105 | 저장소 초기 구조 | 완료 |
| moonlight | `backend/newsletter.py` — LangGraph 파이프라인 (리서치→작성→검수→승인→발송) | 단독 CLI로 동작 |
| dynapark-yj | `frontend/` — 대시보드 UI + FastAPI + LangGraph 껍데기 | UI 완성, **내용은 전부 가짜 데이터** |
| **노희선(나)** | `backend/` — RSS 수집 + RAG 엔진 + API | 엔진 완성, **연결 안 됨** |

### 핵심 상황

프론트엔드 `agent_graph.py`의 리서치 노드는 이렇게 되어 있다.

```python
sources = [
    {"title": f"{primary_kw} 최신 기술 동향...", "domain": "techinsights.io",
     "url": f"https://techinsights.io/reports/..."},   # 존재하지 않는 주소
]
```

**하드코딩된 가짜 기사다.** LLM 호출도 없고 RSS도 없다.
화면과 워크플로 구조는 다 만들어져 있으니, **그 안에 들어갈 진짜 엔진을 내가 넣으면 된다.**

---

## 앞서 정리했던 3가지 미결 사항

| # | 항목 | 현재 상태 |
|---|---|---|
| 1 | RSS 피드 소스 | **결정 완료** — 국내 16개 매체 검증 후 확정 |
| 2 | 이메일 수신자 관리 | **미결** — 아직 정해야 함 |
| 3 | 발송 주기 | **미결** — 프론트가 요구 형식은 정해둠 |

### 1. RSS 소스 — 끝났다

연합뉴스, 연합뉴스_경제, 한겨레, 경향신문, 동아일보, 조선일보, 서울신문,
매일경제, 매일경제_경제, 머니투데이, 뉴시스, 전자신문, 전자신문_IT,
ZDNet코리아, 노컷뉴스, 오마이뉴스 — 16곳.

- 네이버 RSS: 서비스 종료 → 제외
- 구글뉴스: 링크가 리다이렉트라 원문 접근 불가 → 제외
- 본문 크롤링 99% 성공 (평균 900자)

### 2. 이메일 수신자 관리 — 결정 필요

프론트에는 수신자 화면이 **없다.** 키워드 구독(`/api/keywords`)만 있다.
즉 "누구에게 보낼지"는 내가 정해야 한다.

| 방식 | 장점 | 단점 | 추천 |
|---|---|---|---|
| **JSON 파일** | 바로 만들 수 있음, 코드 3줄 | 동시 수정에 취약 | ⭐ 과제용으로 충분 |
| SQLite | 검색·수정 편함, 구독 이력 관리 | 스키마 설계 필요 | 시간 남으면 |
| 외부 DB | 실서비스용 | 과제엔 과함 | ✕ |

> 권장: `backend/subscribers.json` 하나. 나중에 SQLite로 옮기기 쉽다.

### 3. 발송 주기 — 프론트가 형식을 정해뒀다

`frontend/models.py`:

```python
class ScheduleConfig(BaseModel):
    frequency: "daily" | "weekly" | "biweekly" | "monthly"
    dispatch_time: str = "08:30"
    days_of_week: List[str] = ["mon", "wed", "fri"]
```

프론트는 이 값을 저장만 하고 **실제로 시간에 맞춰 돌리는 기능이 없다.**
그 스케줄러가 내 몫이다.

| 방식 | 설명 | 추천 |
|---|---|---|
| **APScheduler** | FastAPI 안에서 도는 파이썬 스케줄러. 서버 켜두면 알아서 실행 | ⭐ |
| 윈도우 작업 스케줄러 | OS가 스크립트 실행. 서버 안 켜도 됨 | 대안 |
| 수동 실행 | 발표 때 버튼으로 시연 | 시간 없으면 |

---

## 해야 할 일 (우선순위 순)

### A. 연결 구조 정하기 — 가장 먼저

**문제:** FastAPI 서버가 두 개인데 **둘 다 `main.py`이고 둘 다 8000번 포트**다. 지금 상태로는 동시에 못 켠다.

```
frontend/main.py   :8000   /api/*  + 대시보드 화면
backend/main.py    :8000   /rag/*  + /generate      ← 충돌
```

| 방안 | 구조 | 평가 |
|---|---|---|
| **A-1. 분리 (권장)** | 백엔드 8001, 프론트 8000. 프론트가 HTTP로 백엔드 호출 | ⭐ 역할 분담 명확, 서로 코드 안 건드림 |
| A-2. 통합 | 한 서버에 라우터 두 개 등록 | 파일명 충돌 정리 필요 |
| A-3. 직접 import | 프론트가 백엔드 모듈을 직접 불러씀 | 폴더가 달라 경로 설정 번거로움 |

**할 일**
- [ ] 백엔드 포트를 8001로 변경
- [ ] CORS 허용 추가 (브라우저가 다른 포트 호출을 막기 때문)
- [ ] 프론트 담당자와 "어느 주소를 부를지" 합의

---

### B. 프론트가 요구하는 형식으로 응답 맞추기

프론트 `models.py`가 기대하는 모양과 내 현재 응답이 다르다.

| 프론트가 원하는 것 | 내 현재 응답 | 할 일 |
|---|---|---|
| `ResearchSource` (title, domain, summary, url) | `sources` (title, source, link, published) | 필드명 변환 |
| `article_html` (HTML) | `newsletter` (마크다운) | **마크다운 → HTML 변환** |
| `AuditReport` (readability / fact_accuracy / coherence 점수) | **없음** | **검수 기능 신규 개발** |
| `NewsletterDraft` (id, status, score, tags…) | 없음 | 초안 모델 추가 |

**할 일**
- [ ] 마크다운 → HTML 변환 (`markdown` 라이브러리 한 줄이면 됨)
- [ ] `ResearchSource` 형식 변환 함수
- [ ] **검수(품질 평가) 기능 개발** ← 아래 C 참고

---

### C. 검수 기능 — 백엔드에 없는 기능

프론트는 초안마다 점수(가독성·사실정확도·일관성)를 화면에 띄운다.
그런데 지금 그건 하드코딩된 숫자(95, 94, 96)다.

**다행히 moonlight가 만든 `backend/newsletter.py`에 이미 있다.**

```python
class ReviewResult(BaseModel):
    passed: bool
    score: int          # 0~100
    feedback: list[str]

def review_newsletter(state): ...   # 사실성 35 / 출처 25 / 구성 20 / 독자적합 20
```

**할 일**
- [ ] `newsletter.py`의 검수 로직을 떼어내 `rag_engine.py`에서 쓸 수 있게 정리
- [ ] 점수를 프론트 형식(readability / fact_accuracy / coherence)으로 매핑
- [ ] 팀원(moonlight)에게 코드 재사용해도 되는지 확인

---

### D. 키워드 기반 수집

프론트는 사용자가 키워드를 등록하는 화면(`/api/keywords`)을 준다.
내 RAG는 검색어로 찾는 기능이 이미 있어서(`rag.summarize(topic=키워드)`) **거의 다 됐다.**

**할 일**
- [ ] 키워드 목록을 받아 각각 요약하는 엔드포인트
- [ ] 키워드 저장소 (`keywords.json`)

---

### E. 초안 저장·상태 관리

프론트가 요구하는 흐름:

```
생성 → pending(승인 대기) → approve → 발송
                          → revise  → 다시 작성
```

지금 내 백엔드는 만들고 바로 돌려줄 뿐, **저장하지 않는다.**

**할 일**
- [ ] 초안 저장 (`drafts.json` 또는 SQLite)
- [ ] `GET /drafts`, `GET /drafts/{id}`
- [ ] `POST /drafts/{id}/approve`, `POST /drafts/{id}/revise`

---

### F. 이메일 발송 연결

`email_utils.py`에 발송 기능은 이미 있다 (`EmailService`, `EmailTemplate`).
**빠진 건 "누구에게" 뿐이다.**

**할 일**
- [ ] 수신자 저장소 (`subscribers.json`)
- [ ] 구독/해지 엔드포인트
- [ ] 승인된 초안을 실제로 발송
- [ ] Gmail 앱 비밀번호 발급 후 `.env`에 설정 → **실제 발송 1회 테스트**

---

### G. 스케줄 발송

**할 일**
- [ ] APScheduler 설치·연동
- [ ] `ScheduleConfig` 저장·조회
- [ ] 정해진 시각에 수집 → 요약 → 발송 자동 실행

---

## 체크리스트

| 순서 | 작업 | 난이도 | 비고 |
|---|---|---|---|
| 1 | 포트 분리 + CORS | 쉬움 | 먼저 해야 나머지 테스트 가능 |
| 2 | 마크다운 → HTML | 쉬움 | 라이브러리 한 줄 |
| 3 | 응답 형식 변환 | 보통 | 프론트 `models.py` 기준 |
| 4 | 검수 기능 이식 | 보통 | moonlight 코드 재사용 |
| 5 | 키워드 수집 | 쉬움 | RAG에 이미 있음 |
| 6 | 초안 저장·상태 | 보통 | JSON으로 시작 |
| 7 | 이메일 발송 | 보통 | 앱 비밀번호 필요 |
| 8 | 스케줄러 | 보통 | 시간 부족하면 수동 실행으로 시연 |

---

## 팀원과 합의할 것

1. **연결 방식** — 포트 분리(A-1)로 갈지, 한 서버로 합칠지
2. **프론트 담당자** — `agent_graph.py`의 가짜 데이터를 내 API 호출로 바꿔줄 수 있는지
3. **moonlight** — `newsletter.py`의 검수 로직 재사용 가능한지
4. **발표 시연 범위** — 스케줄 자동발송까지 보여줄지, 수동 실행으로 할지

---

## 이미 끝난 것

- RSS 수집 (16개 매체, 152건)
- 본문 크롤링 (99% 성공, 458자 → 900자)
- RAG 색인·검색 (FAISS)
- 리서치 답변 (근거 번호 + 원문 링크)
- 요약 3종 (brief / newsletter / deep)
- 환각 방지 확인
- API 7개 (`/rag/*`)
- 문제 해결 기록 (`TROUBLESHOOTING.md`)
