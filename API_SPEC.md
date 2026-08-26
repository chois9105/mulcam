# API 명세 — 프론트엔드 연동용

최종 갱신: 2026-08-26 · 백엔드: 노희선

| 환경 | 주소 |
|---|---|
| **배포 서버** | `https://mulcam.1435.co.kr` — 문서: [`/docs`](https://mulcam.1435.co.kr/docs) |
| 로컬 | `http://127.0.0.1:8001` |

**모든 엔드포인트는 `/api` 로 시작한다.** (2026-08-25 팀장 요청)
요청·응답은 `application/json`, 인코딩 `utf-8`.

> 이 문서는 **실제 배포된 코드와 일치**한다. `/docs` 에서 직접 눌러볼 수도 있다.

---

## 화면 버튼 = 엔드포인트 3개

```
① 키워드/문장 입력  →  실시간 검색 → 리서치 → 요약본 생성 → 검수
                        ↓
② 읽어보고  [수정 요청]  또는  [최종 승인 + 주기]
                        ↓
                     메일 발송
```

| # | 화면 버튼 | 엔드포인트 |
|---|---|---|
| 1 | 🚀 뉴스레터 요청 | `POST /api/newsletter/request` |
| 2 | ↺ 수정 요청 | `POST /api/drafts/{draft_id}/revise` |
| 3 | ✅ 최종 승인 | `POST /api/drafts/{draft_id}/approve` |

화면에 데이터를 채울 때 쓰는 조회용도 있다.

| 메서드 | 경로 | 용도 |
|---|---|---|
| GET | `/api/drafts` | 목록 (② 드롭다운, ③ 카드 목록) |
| GET | `/api/drafts/{draft_id}` | 상세 |
| GET | `/api/status` | 백엔드가 살아있는지 · 저장소 · 스케줄러 |

---

## 1. 뉴스레터 요청

```
POST /api/newsletter/request
```

### 요청

```json
{ "request_text": "생성형 AI와 LangGraph의 이번 주 주요 뉴스를 실무자 관점에서 5개 정도 정리해 주세요." }
```

| 항목 | 필수 | 설명 |
|---|---|---|
| `request_text` | ✅ | 키워드도 되고 문장도 된다. 최소 2자 |

짧게 `"AI 반도체"` 만 넣어도 되고, 문장으로 길게 써도 된다.
백엔드가 문장에서 검색어·독자·기사 수를 뽑아낸다.

### 응답 — 요약본 한 덩어리

```json
{
  "id": "draft_20260826_091545",
  "title": "AI와 IT 분야 주요 뉴스 브리핑",
  "summary": "사용자 요청 '...'을 반영하여 리서치·작성·검수 에이전트가 구성한 맞춤형 뉴스레터 초안입니다.",
  "score": 85,
  "score_grade": "B 통과",
  "status": "pending",
  "frequency": null,
  "frequency_label": null,
  "created_at": "2026.08.26 09:15",
  "revision_count": 0,
  "pipeline": ["keyword_search", "research", "newsletter", "review"],

  "article_html": "<div class=\"article-hero-box\">…</div>",
  "markdown": "# AI IT 주요 뉴스\n\n**IPO 앞둔 오픈AI…** [1]\n…",

  "audit_report": {
    "readability": 90,
    "fact_accuracy": 85,
    "coherence": 85,
    "reviewer_comment": "3번 항목에 근거 번호가 빠졌습니다.",
    "loop_count": "0회"
  },

  "sources": [
    {
      "title": "IPO 앞둔 오픈AI, 데이터센터 총괄도 퇴사",
      "domain": "zdnet.co.kr",
      "summary": "ZDNet코리아",
      "url": "https://zdnet.co.kr/view/?no=..."
    }
  ]
}
```

### 화면 어디에 넣나

| 화면 | 응답 필드 |
|---|---|
| 카드 제목 | `title` |
| 카드 설명 | `summary` |
| `검수 85점 · 승인 대기 · 주기 매일 · 2026.08.26 09:15` | `score` · `status` · `frequency_label` · `created_at` |
| 상세 — 본문 | `article_html` (그대로 넣으면 됨) |
| 상세 — 검수 결과 | `audit_report` |
| 상세 — 참고 기사 | `sources` (`url` 로 원문 이동) |
| ② 드롭다운 | `id` + `title` |

### 걸리는 시간

**10~20초.** 화면에 진행 표시를 두는 편이 좋다.
(요청 분석 → 기사 검색 → 요약 → 한국어 다듬기 → 검수)

### 오류

| 코드 | 언제 | 화면에 보여줄 말 |
|---|---|---|
| 409 | 모아둔 기사가 없거나 API 키 문제 | 뉴스를 아직 모으지 못했습니다. 잠시 후 다시 시도해 주세요 |
| 404 | 관련 기사를 못 찾음 | 그 키워드로 찾은 뉴스가 없습니다 |
| 500 | 생성 실패 | 생성에 실패했습니다. 다시 시도해 주세요 |

---

## 2. 수정 요청

화면 ②의 **"이렇게 바꾸어주세요"** 한 칸을 그대로 보낸다.

```
POST /api/drafts/{draft_id}/revise
```

### 요청

```json
{ "direction": "너무 기술적인 표현은 줄이고, 핵심 뉴스 5개를 먼저 보여준 뒤 각 항목을 실무자가 이해하기 쉽게 설명해 주세요." }
```

| 항목 | 필수 | 설명 |
|---|---|---|
| `direction` | ✅ | 어떻게 바꿔달라는 요청. 최소 2자 |

### 응답

**1번과 똑같은 모양**이다. 화면은 카드만 갈아끼우면 된다.
`revision_count` 가 1 늘어나고 `score` 가 다시 매겨진다.

기사를 새로 찾지 않고 **직전 응답을 만든 리서치 결과와 본문을 기준으로 다시 쓴다.**

### 오류

| 코드 | 언제 |
|---|---|
| 404 | 그 `draft_id` 가 없음 |
| 409 | 이미 승인된 것은 수정할 수 없음 |
| 500 | 수정 실패 |

---

## 3. 최종 승인 (+ 주기)

화면 ②의 **[최종 승인]** 과 그 옆의 **주기**를 함께 보낸다.

```
POST /api/drafts/{draft_id}/approve
```

### 요청

```json
{
  "frequency": "daily",
  "approved_template": "<article>사용자가 최종 승인한 HTML...</article>"
}
```

| 항목 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `frequency` | — | `daily` | `once` `daily` `weekly` `biweekly` `monthly` |
| `approved_template` | — | 현재 초안 HTML | 사용자가 최종 승인한 템플릿 HTML |

로그인 화면이 없는 단일 사용자 서비스이므로 승인 시 사용자 이메일은 항상
`contact@1435.co.kr` 로 저장된다. `frequency`, `approved_template`, `user_email`,
다음 실행 시각은 MySQL `drafts` 테이블에 영속 저장된다.

### 응답

1번과 같은 모양에 아래가 더해진다.

```json
{
  "status": "approved",
  "frequency": "daily",
  "frequency_label": "매일",
  "approved_at": "2026.08.26 09:20",
  "schedule_id": "draft_20260826_091545",
  "message": "승인되었습니다. 주기: 매일",
  "send_result": {
    "sent": true,
    "count": 3,
    "to": ["a@gmail.com", "b@gmail.com", "c@gmail.com"],
    "subject": "[뉴스레터] AI와 IT 분야 주요 뉴스 브리핑"
  }
}
```

### 승인하면 바로 발송된다

`send_result` 로 결과를 알 수 있다.

| 상황 | `send_result` |
|---|---|
| 발송 성공 | `{ "sent": true, "count": 3, ... }` |
| 안전장치 켜짐 | `{ "dry_run": true, "message": "MAIL_DRY_RUN=true 라 …" }` |
| 설정 미비 | `{ "sent": false, "reason": "…", "problems": [...] }` |

> `MAIL_DRY_RUN=true` 면 실제로 나가지 않는다. 시연 중 실수 방지용이다.

`frequency` 가 `once` 가 아니면, 이후 그 주기마다 같은 요청으로
뉴스를 새로 모아 요약본을 만들어 **승인 대기**에 올린다. (사람 승인 없이 보내지 않는다)

### 오류

| 코드 | 언제 |
|---|---|
| 404 | 그 `draft_id` 가 없음 |
| 409 | 이미 승인된 요약본 |

---

## 4. 조회

### 목록

```
GET /api/drafts
GET /api/drafts?status=pending
```

```json
{ "count": 3, "drafts": [ { …1번과 같은 모양… } ] }
```

`status` 는 `all`(기본) `pending` `approved` `rejected` `sent`.

### 상세

```
GET /api/drafts/{draft_id}
```

### 백엔드 상태

```
GET /api/status
```

```json
{
  "storage": { "mode": "mysql", "persistent": true, "note": "MySQL 에 저장됩니다." },
  "scheduler": { "running": true, "jobs": [ { "id": "collect_news", "다음_실행": "2026-08-26 07:00" } ] },
  "drafts": 3,
  "schedules": 1
}
```

---

## 상태 값

```
pending (승인 대기) ──approve──▶ approved ──발송──▶ sent
   ▲
   └──── revise ────┘
```

| 값 | 화면 표시 |
|---|---|
| `pending` | 승인 대기 |
| `approved` | 승인됨 |
| `sent` | 발송 완료 |
| `rejected` | 거절됨 |

---

## 참고 — 그 외 엔드포인트

화면에서 부를 일은 없지만 `/docs` 에 보인다.

| 경로 | 용도 |
|---|---|
| `POST /api/news/collect` | 뉴스 수집을 지금 실행 (1~2분). 평소엔 스케줄러가 함 |
| `POST /api/graph/start` | **LangGraph** 실행 — 인간 승인 노드에서 중단 |
| `POST /api/graph/{thread_id}/resume` | approve/revise/reject 로 재개 |
| `GET /api/graph/{thread_id}` | 지금 어느 노드에서 멈춰 있나 |
| `/api/rag/*` | 개발·확인용 (수집·검색·요약을 따로 호출) |
| `GET /api/health` | 살아있는지 확인 |

> `graph` 계열은 과제 요구사항(Conditional Edges, Human-in-the-Loop)을
> 실제로 보여주기 위한 것이다. 화면 흐름과 하는 일은 같다.

---

## 빠른 시험

```bash
curl -X POST https://mulcam.1435.co.kr/api/newsletter/request \
  -H "Content-Type: application/json" \
  -d '{"request_text":"AI 반도체 관련 뉴스를 정리해 주세요"}'
```

또는 [`/docs`](https://mulcam.1435.co.kr/docs) 에서 **Try it out** 버튼으로 바로 눌러볼 수 있다.
