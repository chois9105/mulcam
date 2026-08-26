# 뉴스레터 에이전트 (RSS + RAG)

국내 언론사 RSS를 모아 본문까지 가져온 뒤, RAG로 근거 있는 뉴스레터를 만든다.

```
RSS 수집 → 본문 크롤링 → 임베딩·색인(FAISS) → 검색 → LLM 답변/요약
```

## 왜 RAG인가

LLM은 학습 시점 이후의 뉴스를 모른다. 오늘 수집한 기사를 검색해서 프롬프트에
직접 넣어주면, 모델이 지어내지 않고 **실제 기사에 근거해** 답한다.
모든 응답에는 근거 기사 번호 `[1]`과 원문 링크가 붙는다.

## 검증 결과 (2026-08-25)

| 항목 | 결과 |
|---|---|
| 등록 피드 | 16개 (연합·한겨레·경향·동아·조선·서울·매경·머니투데이·뉴시스·전자신문·ZDNet·노컷·오마이 등) |
| 수집 | 152건 |
| RSS가 주는 요약 | 평균 458자 — **요약 재료로 부족** |
| 링크 따라가 본문 수집 | 155/156 성공 (99%), 평균 900자 |
| 리서치·요약·환각방지 | 정상 |

### 확인된 제약

- **RSS는 본문 전체를 주지 않는다.** 연합뉴스는 63자 요약만 준다.
  그래서 `article_fetcher.py`가 링크를 따라가 본문을 긁어온다.
- **구글뉴스는 제외했다.** 링크가 `news.google.com/rss/articles/...` 리다이렉트라
  상세 페이지로 바로 갈 수 없고 본문도 못 가져온다.
- **네이버 RSS는 서비스 종료.** `rss.naver.com` 도메인 자체가 없다.
- 조선일보·머니투데이 일부 기사는 봇 차단으로 본문 실패 → RSS 요약으로 대체된다.
- 부고·인사·헤드라인 목록 기사는 수집 단계에서 걸러낸다 (`SKIP_TITLE`).

## 요약 3종

| style | 이름 | 형식 | 참고 기사 |
|---|---|---|---|
| `brief` | 짧은 브리핑 | 한 줄 + 핵심 3가지, 200자 이내 | 5건 |
| `newsletter` | 표준 뉴스레터 | 이슈 3~5개 (소제목 + 설명) + 오늘의 한 줄 | 8건 |
| `deep` | 심층 분석 | 무슨 일이 / 왜 중요한가 / 함께 볼 흐름 / 참고 기사 | 12건 |

## API

수집(느림)과 생성(빠름)을 분리했다. `/rag/build`를 하루 1~2회 돌려 색인을 만들고,
그 뒤 `/rag/ask`·`/rag/summarize`를 여러 번 빠르게 호출한다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/rag/build` | RSS 수집 → 본문 크롤링 → 색인 생성 (1~2분) |
| GET | `/rag/status` | 색인 준비 상태·등록 피드 확인 |
| GET | `/rag/news` | 수집된 원본 뉴스 JSON (링크 포함, 상세페이지 이동용) |
| POST | `/rag/ask` | 리서치 — 질문에 기사 근거로 답변 |
| POST | `/rag/summarize` | 요약 — style 로 3종 중 선택 |
| POST | `/rag/draft` | 요약+검수 → 프론트 `NewsletterDraft` 형식 |
| GET | `/rag/drafts` | 생성된 초안 목록 |
| GET | `/rag/drafts/{id}` | 초안 상세 |
| POST | `/rag/summarize/compare` | 3종을 한 번에 생성해 비교 |
| GET | `/rag/styles` | 스타일 목록 |

기존 엔드포인트(`/generate`, `/news/rss`, `/newsletter/from-rss`, `/validate-emails`)도 유지된다.

## 실행

```bash
pip install -r requirements.txt
cp .env.example .env          # .env 에 OPENAI_API_KEY 입력
python -m uvicorn main:app --reload --port 8001
```

문서: http://127.0.0.1:8001/docs

> 백엔드는 **8001번**을 쓴다. 프론트엔드(`frontend/main.py`)가 8000번을 쓰기 때문이다.
> 두 서버를 동시에 켜야 연동 테스트가 된다.

### 사용 예

```bash
# 1) 색인 생성 (처음 한 번)
curl -X POST http://127.0.0.1:8001/rag/build \
  -H "Content-Type: application/json" \
  -d '{"limit_per_feed": 15, "fetch_full_text": true}'

# 2) 리서치
curl -X POST http://127.0.0.1:8001/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "오늘 반도체 관련 소식은?", "k": 5}'

# 3) 요약 (스타일 선택)
curl -X POST http://127.0.0.1:8001/rag/summarize \
  -H "Content-Type: application/json" \
  -d '{"topic": "오늘의 IT 뉴스", "style": "deep"}'
```

## 전체 검증

```bash
python test_rag.py
```

수집 건수, 본문 확보율, 리서치 답변, 요약 3종, 환각 방지까지 한 번에 확인한다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `rss_collector.py` | RSS 수집, 중복 제거, 정형 기사 필터 |
| `article_fetcher.py` | 링크를 따라가 기사 본문 추출 |
| `rag_engine.py` | 임베딩·검색·답변·요약 3종 |
| `html_render.py` | 마크다운 → HTML (대시보드 조각 / 이메일 문서) |
| `reviewer.py` | 검수 에이전트 (사실성35/출처25/구성20/독자20) |
| `adapters.py` | 프론트엔드 형식 변환 (`NewsletterDraft`) |
| `rag_api.py` | RAG 엔드포인트 |
| `main.py` | FastAPI 앱 (라우터 등록) |
| `project_newsletter.py` | LLM 단독 뉴스레터 생성 (RAG 없음) |
| `newsletter.py` | LangGraph 파이프라인 버전 |
| `email_utils.py` | 이메일 발송 |
| `test_rag.py` | 전체 검증 스크립트 |

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `OPENAI_API_KEY` | — | 필수 |
| `OPENAI_MODEL` | `gpt-4o-mini` | 답변·요약 모델 |
| `OPENAI_EMBED_MODEL` | `text-embedding-3-small` | 임베딩 모델 |
| `RAG_INDEX_DIR` | `faiss_index` | 색인 저장 위치 |
