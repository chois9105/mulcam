# API 명세 — 엔드포인트 3개

확정: 2026-08-25 회의
백엔드 주소: `http://127.0.0.1:8001`
화면 주소: `http://127.0.0.1:8000`

---

## 전체 흐름

```
① 키워드 입력
      ↓  자동으로 뉴스를 찾아 요약
   요약본 확인
      ↓
② 승인 또는 거절
      ↓  승인한 경우만
③ 주기 설정 → 발송
```

거절하면 거기서 끝난다. 주기 설정 화면으로 넘어가지 않는다.

| # | 이름 | 엔드포인트 | 화면 위치 |
|---|---|---|---|
| 1 | 주제 선정 | `POST /api/newsletter/request` | ① 뉴스레터 요청 |
| 2 | 승인 | `POST /api/drafts/{id}/decision` | ② 승인 / 거절 |
| 3 | 주기 설정과 발송 | `POST /api/schedule` | ① 주기 |

모든 요청·응답은 `application/json`, 인코딩은 `utf-8`.

### 출력 형태는 하나

회의에서 **`a. 기사 간단 요약`** 하나만 쓰기로 정했다.
따라서 요청에 형태를 고르는 항목이 없다. 항상 아래 모양으로 나온다.

```markdown
# 생성형 AI와 LangGraph 관련 기사 요약

**공공 현안 해결할 AI 찾는다…정부, 민간 경진대회 개최** [1]
정부가 교통사고 분석, 딥보이스 탐지 등 사회문제 해결을 위해 민간 AI
전문가들의 기술과 아이디어를 활용하는 경진대회를 개최한다.

**배경훈 "AI 모델은 국가 안보"…독자 AI 글로벌 톱티어 도전** [2]
정부는 독자 AI 모델을 세계 최고 수준으로 고도화하고, 내년에는 최상위급
프론티어 AI 모델 개발에 도전할 계획이다.
```

기사 하나당 한 항목. `[1]` `[2]` 번호는 응답의 `sources` 와 이어지고, 거기에 원문 링크가 있다.

---

## 1. 주제 선정

사용자가 키워드나 문장을 넣으면, 관련 기사를 찾아 요약해서 돌려준다.

```
POST /api/newsletter/request
```

### 요청

```json
{
  "request_text": "생성형 AI와 LangGraph의 이번 주 주요 뉴스를 실무자 관점에서 정리해 주세요."
}
```

| 항목 | 필수 | 설명 |
|---|---|---|
| `request_text` | 필수 | 키워드도 되고 문장도 된다. 예) `"AI 반도체"` 또는 위 예시 문장 |

> 짧은 키워드만 넣어도 되고, 문장으로 길게 써도 된다.
> 백엔드가 문장에서 키워드·독자·개수를 뽑아낸다.

### 응답

```json
{
  "id": "draft_20260825_165230",
  "title": "생성형 AI와 LangGraph 관련 기사 요약",
  "summary": "정부의 AI 경진대회 개최, 독자 AI 모델 고도화 계획 등 3건",
  "score": 93,
  "score_grade": "A 양호",
  "status": "pending",
  "created_at": "2026.08.25 16:52",

  "article_html": "<div class=\"article-hero-box\">…</div>",

  "audit_report": {
    "readability": 95,
    "fact_accuracy": 92,
    "coherence": 93,
    "reviewer_comment": "3번 항목에 근거 번호가 빠졌습니다.",
    "loop_count": "0회"
  },

  "sources": [
    {
      "title": "공공 현안 해결할 AI 찾는다…정부, 민간 경진대회 개최",
      "domain": "zdnet.co.kr",
      "summary": "ZDNet코리아",
      "url": "https://zdnet.co.kr/view/?no=20260825135245"
    }
  ],

  "parsed": {
    "keywords": ["생성형 AI", "LangGraph"],
    "audience": "실무자"
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
| ② 대상 드롭다운 | `id` + `title` |

### 백엔드 내부 동작

```
입력한 키워드·문장
  → 1. 요청 분석    키워드·독자를 뽑는다
  → 2. 기사 검색    미리 모아둔 기사에서 관련된 것만 고른다
  → 3. 기사별 요약  기사 하나당 제목 + 한두 문장
  → 4. 한국어 다듬기
  → 5. 검수 채점
  → 6. 저장 (status = pending)
```

응답까지 **10~20초** 걸린다. 화면에 진행 표시를 두는 편이 좋다.

### 오류

| 코드 | 언제 | 화면에 보여줄 말 |
|---|---|---|
| 400 | `request_text` 가 비었을 때 | 키워드나 원하는 내용을 입력해 주세요 |
| 404 | 관련 기사를 못 찾았을 때 | 그 키워드로 찾은 뉴스가 없습니다. 다른 키워드로 시도해 주세요 |
| 409 | 모아둔 기사가 아예 없을 때 | 뉴스를 아직 모으지 못했습니다. 잠시 후 다시 시도해 주세요 |
| 500 | AI 호출 실패 | 생성에 실패했습니다. 다시 시도해 주세요 |

---

## 2. 승인

사용자가 요약본을 읽고 판단한다. **승인 / 거절 / 수정 요청** 세 갈래를 한 엔드포인트로 받는다.
사람이 내리는 한 번의 판단이기 때문이다.

```
POST /api/drafts/{id}/decision
```

### 요청 — 승인

```json
{ "action": "approve" }
```

### 요청 — 거절

```json
{ "action": "reject" }
```

### 요청 — 수정 요청

```json
{
  "action": "revise",
  "reason":    "내용이 너무 기술적이고 핵심 뉴스가 잘 보이지 않습니다",
  "direction": "쉽게 줄이고 핵심 뉴스 5개를 먼저 보여주세요"
}
```

| 항목 | 필수 | 설명 |
|---|---|---|
| `action` | 필수 | `approve` / `reject` / `revise` |
| `reason` | revise 일 때 | 화면의 **"왜 마음에 안 드나요?"** |
| `direction` | revise 일 때 | 화면의 **"어떻게 바꿔 주세요?"** |

> `reason` 과 `direction` 을 나눠 받는다. 문제와 지시를 구분해서 주면 AI가 더 정확하게 고친다.

### 응답 — 승인

```json
{
  "id": "draft_20260825_165230",
  "status": "approved",
  "approved_at": "2026.08.25 17:04",
  "next_step": "schedule",
  "message": "승인되었습니다. 발송 주기를 설정해 주세요."
}
```

`next_step` 이 `schedule` 이면 화면은 **주기 설정으로 넘어간다.**

### 응답 — 거절

```json
{
  "id": "draft_20260825_165230",
  "status": "rejected",
  "next_step": null,
  "message": "거절되었습니다."
}
```

거절하면 **여기서 끝난다.** 주기 설정으로 넘어가지 않는다.

### 응답 — 수정

새로 쓰고 다시 검수한 요약본 전체를 돌려준다. 1번 응답과 같은 모양이라 카드만 갈아끼우면 된다.

```json
{
  "id": "draft_20260825_165230",
  "title": "생성형 AI와 LangGraph 관련 기사 요약",
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
| 404 | 그 `id` 의 요약본이 없을 때 |
| 409 | 이미 승인·거절된 것을 다시 처리하려 할 때 |
| 422 | `revise` 인데 `reason` 과 `direction` 이 모두 비었을 때 |

---

## 3. 주기 설정과 발송

**승인된 요약본에 대해서만** 부른다. 언제 보낼지 정하면 저장하고, 그 시각에 발송한다.

```
POST /api/schedule
```

### 요청

```json
{
  "draft_id": "draft_20260825_165230",
  "frequency": "daily",
  "dispatch_time": "08:30",
  "days_of_week": ["mon", "wed", "fri"],
  "recipients": ["linkcontent7@gmail.com"],
  "send_now": false
}
```

| 항목 | 필수 | 설명 |
|---|---|---|
| `draft_id` | 필수 | **승인된** 요약본의 id |
| `frequency` | 필수 | `once` `daily` `weekly` `biweekly` `monthly` |
| `dispatch_time` | `once` 아닐 때 | `HH:MM` 24시간 |
| `days_of_week` | `weekly` 일 때 | 요일 목록 |
| `recipients` | 필수 | 받는 사람 메일 주소 |
| `send_now` | 선택 | `true` 면 즉시 한 번 발송 (시연용) |

> `frequency` 를 `once` 로 하면 반복 없이 한 번만 보낸다.
> 같은 키워드로 계속 받고 싶으면 `daily` 등을 고른다. 정해진 시각마다
> **같은 키워드로 뉴스를 새로 모아 요약본을 만들어** 승인 대기에 올린다.

### 응답

```json
{
  "schedule_id": 1,
  "draft_id": "draft_20260825_165230",
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
| 404 | `draft_id` 가 없을 때 | 요약본을 찾을 수 없습니다 |
| 409 | **승인되지 않은** 요약본일 때 | 먼저 승인해 주세요 |
| 422 | 메일 주소 형식이 틀림 | 메일 주소를 확인해 주세요 |
| 500 | 메일 서버 접속 실패 | 발송 설정을 확인해 주세요 |

---

## 상태 값

```
                    ┌──── reject ────▶ rejected  (끝)
                    │
pending (승인 대기) ─┼──── approve ───▶ approved ──발송──▶ sent
   ▲                │
   └──── revise ────┘
```

| 값 | 화면 표시 | 다음에 할 수 있는 일 |
|---|---|---|
| `pending` | 승인 대기 | 승인 · 거절 · 수정 요청 |
| `approved` | 승인됨 | 주기 설정 |
| `rejected` | 거절됨 | 없음 |
| `sent` | 발송 완료 | 없음 |

---

## 화면 연결 확인용

버튼은 아니지만, 프론트가 백엔드가 켜져 있는지 확인할 때 쓴다.

```
GET /health
→ { "status": "healthy", "port": 8001, ... }
```

---

## 나중에 추가할 것

| 엔드포인트 | 언제 필요한가 |
|---|---|
| `GET /api/drafts` | 브라우저를 새로고침해도 목록이 남아야 할 때 |
| `POST /api/news/collect` | 기사 수집을 수동으로 돌릴 때 (평소엔 스케줄러가 함) |

> 지금은 응답에 요약본 전체가 담겨 있어서, 프론트가 그걸 들고 있으면 조회 엔드포인트가 필요 없다.
> 다만 **새로고침하면 목록이 사라진다.** MySQL 을 붙일 때 `GET /api/drafts` 를 추가하면 해결된다.
