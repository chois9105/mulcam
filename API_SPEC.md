# API 명세 — 엔드포인트 3개

확정: 2026-08-25 회의
백엔드 주소: `http://127.0.0.1:8001`
화면 주소: `http://127.0.0.1:8000`

| # | 이름 | 엔드포인트 | 화면 위치 |
|---|---|---|---|
| 1 | 주제 선정 | `POST /api/newsletter/request` | ① 뉴스레터 요청 |
| 2 | 승인 | `POST /api/drafts/{id}/decision` | ② 수정 요청 / 최종 승인 |
| 3 | 주기 설정과 발송 | `POST /api/schedule` | ① 주기 |

모든 요청·응답은 `application/json`, 인코딩은 `utf-8`.

---

## 1. 주제 선정

사용자가 원하는 뉴스레터를 **문장으로** 적고 요청한다.
백엔드는 문장을 해석해 기사를 찾고, 글을 쓰고, 다듬고, 검수까지 마쳐서 돌려준다.

```
POST /api/newsletter/request
```

### 요청

```json
{
  "request_text": "생성형 AI와 LangGraph의 이번 주 주요 뉴스를 실무자 관점에서 5개 정도 정리해 주세요.",
  "frequency": "daily"
}
```

| 항목 | 필수 | 설명 |
|---|---|---|
| `request_text` | 필수 | 사용자가 입력한 문장 그대로 |
| `frequency` | 선택 | `daily` `weekly` `biweekly` `monthly`. 화면 ①의 주기 |

### 응답

```json
{
  "id": "draft_20260825_165230",
  "title": "LangGraph 맞춤형 뉴스 브리핑",
  "summary": "사용자 요청 'LangGraph와 Human-in-the-Loop의 최신 실무 적용 사례를 간단한 뉴스레터로 정리해 주세요.'을 반영하여 리서치·작성·검수 에이전트가 구성한 맞춤형 뉴스레터 초안입니다.",
  "score": 93,
  "score_grade": "A 양호",
  "status": "pending",
  "created_at": "2026.08.25 16:52",

  "article_html": "<div class=\"article-hero-box\">…</div>",

  "audit_report": {
    "readability": 95,
    "fact_accuracy": 92,
    "coherence": 93,
    "reviewer_comment": "핵심 이슈 배치는 좋으나 2번 항목에 근거 번호가 빠졌습니다.",
    "loop_count": "0회"
  },

  "sources": [
    {
      "title": "AI 칩 떠받치는 기판도 품귀…삼성전기·LG이노텍 생산 능력 확대",
      "domain": "chosun.com",
      "summary": "조선일보",
      "url": "https://www.chosun.com/economy/..."
    }
  ],

  "parsed": {
    "keywords": ["생성형 AI", "LangGraph"],
    "audience": "실무자",
    "count": 5,
    "template": "b"
  }
}
```

### 화면에서 쓰는 곳

| 화면 | 응답 필드 |
|---|---|
| ③ 카드 제목 | `title` |
| ③ 카드 설명 | `summary` |
| ③ `검수 93점 · 승인 대기 · 2026.08.25 16:52` | `score` · `status` · `created_at` |
| ③ 상세 펼침 — 본문 | `article_html` (그대로 삽입) |
| ③ 상세 펼침 — 검수 결과 | `audit_report` |
| ③ 상세 펼침 — 참고 기사 | `sources` (`url` 로 원문 이동) |
| ② 대상 드롭다운 | `id` + `title` 을 쌓아서 표시 |

### 백엔드 내부 동작

```
요청 문장
  → 1. 문장 분석    키워드·독자·개수·형태를 뽑는다
  → 2. 기사 검색    미리 모아둔 기사에서 관련된 것만 고른다
  → 3. 뉴스레터 작성
  → 4. 한국어 다듬기
  → 5. 검수 채점
  → 6. 저장 (status = pending)
```

응답까지 **10~20초** 걸린다. 화면에 진행 표시를 두는 편이 좋다.

### 오류

| 코드 | 언제 | 화면에 보여줄 말 |
|---|---|---|
| 400 | `request_text` 가 비었을 때 | 원하는 내용을 입력해 주세요 |
| 409 | 모아둔 기사가 없을 때 | 뉴스를 아직 모으지 못했습니다. 잠시 후 다시 시도해 주세요 |
| 500 | AI 호출 실패 | 생성에 실패했습니다. 다시 시도해 주세요 |

---

## 2. 승인

화면 ②의 버튼 **두 개가 한 엔드포인트**를 쓴다. `action` 으로 구분한다.
사람이 판단하는 단계라, 승인·수정이 같은 결정의 두 갈래이기 때문이다.

```
POST /api/drafts/{id}/decision
```

### 요청 — 최종 승인

```json
{ "action": "approve" }
```

### 요청 — 수정 요청

```json
{
  "action": "revise",
  "reason": "내용이 너무 기술적이고 핵심 뉴스가 잘 보이지 않습니다",
  "direction": "쉽게 줄이고 핵심 뉴스 5개를 먼저 보여주세요"
}
```

| 항목 | 필수 | 설명 |
|---|---|---|
| `action` | 필수 | `approve` 또는 `revise` |
| `reason` | revise 일 때 | 화면의 **"왜 마음에 안 드나요?"** |
| `direction` | revise 일 때 | 화면의 **"어떻게 바꿔 주세요?"** |

> 왜와 어떻게를 나눠 받는다. 문제와 지시를 구분해서 주면 AI가 더 정확하게 고친다.

### 응답 — 승인

```json
{
  "id": "draft_20260825_165230",
  "status": "approved",
  "approved_at": "2026.08.25 17:04",
  "message": "승인되었습니다. 설정된 주기에 맞춰 발송됩니다."
}
```

### 응답 — 수정

**새로 쓰고 다시 검수한 초안 전체**를 돌려준다. 1번 응답과 같은 모양이라, 화면은 카드만 갈아끼우면 된다.

```json
{
  "id": "draft_20260825_165230",
  "title": "LangGraph 맞춤형 뉴스 브리핑",
  "summary": "…",
  "score": 96,
  "status": "pending",
  "revision_count": 1,
  "article_html": "…",
  "audit_report": { "…" },
  "sources": [ "…" ]
}
```

### 오류

| 코드 | 언제 |
|---|---|
| 404 | 그 `id` 의 초안이 없을 때 |
| 409 | 이미 승인된 초안을 다시 수정하려 할 때 |
| 422 | `revise` 인데 `reason` 과 `direction` 이 모두 비었을 때 |

---

## 3. 주기 설정과 발송

언제 보낼지 정한다. 저장하면 그 시각에 자동으로 뉴스레터를 만들어 승인 대기에 올리고,
승인된 것을 발송한다.

```
POST /api/schedule
```

### 요청

```json
{
  "request_text": "생성형 AI와 LangGraph의 이번 주 주요 뉴스를 실무자 관점에서 5개 정도 정리해 주세요.",
  "frequency": "daily",
  "dispatch_time": "08:30",
  "days_of_week": ["mon", "wed", "fri"],
  "recipients": ["linkcontent7@gmail.com"],
  "send_now": false
}
```

| 항목 | 필수 | 설명 |
|---|---|---|
| `request_text` | 필수 | 매번 이 요청으로 뉴스레터를 만든다 |
| `frequency` | 필수 | `daily` `weekly` `biweekly` `monthly` |
| `dispatch_time` | 필수 | `HH:MM` 24시간 |
| `days_of_week` | `weekly` 일 때 | 요일 목록 |
| `recipients` | 필수 | 받는 사람 메일 주소 |
| `send_now` | 선택 | `true` 면 즉시 한 번 발송 (시연용) |

### 응답

```json
{
  "schedule_id": 1,
  "frequency": "daily",
  "dispatch_time": "08:30",
  "next_run_at": "2026-08-26 08:30",
  "recipients": 1,
  "is_active": true,
  "sent_now": false
}
```

### 발송 안전장치

시연 중 실수로 메일이 나가지 않도록 `.env` 에 스위치를 둔다.

```
MAIL_DRY_RUN=true    # true 면 실제로 보내지 않고 기록만 남긴다
```

### 오류

| 코드 | 언제 | 화면에 보여줄 말 |
|---|---|---|
| 422 | 메일 주소 형식이 틀림 | 메일 주소를 확인해 주세요 |
| 500 | 메일 서버 접속 실패 | 발송 설정을 확인해 주세요 |

---

## 상태 값

초안은 세 가지 상태를 오간다.

```
pending  (승인 대기)  ──approve──▶  approved  (승인됨)  ──발송──▶  sent
    ▲                                                              
    └──────────────── revise (다시 작성) ────────────────┘
```

| 값 | 화면 표시 |
|---|---|
| `pending` | 승인 대기 |
| `approved` | 승인됨 |
| `sent` | 발송 완료 |

---

## 화면 연결 확인용

버튼은 아니지만, 프론트가 백엔드가 켜져 있는지 확인할 때 쓴다.

```
GET /health
→ { "status": "healthy", "port": 8001, ... }
```

---

## 나중에 추가할 것

지금은 없어도 되지만, 다음 상황이 되면 필요하다.

| 엔드포인트 | 언제 필요한가 |
|---|---|
| `GET /api/drafts` | 브라우저를 새로고침해도 목록이 남아야 할 때 |
| `POST /api/news/collect` | 기사 수집을 수동으로 돌리고 싶을 때 (평소엔 스케줄러가 함) |

> 지금은 응답에 초안 전체가 담겨 있어서, 프론트가 그걸 들고 있으면 조회 엔드포인트가 필요 없다.
> 다만 **새로고침하면 목록이 사라진다.** MySQL 을 붙일 때 `GET /api/drafts` 를 추가하면 해결된다.
