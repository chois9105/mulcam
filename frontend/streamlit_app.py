"""
streamlit_app.py
Apple HIG 스타일 맞춤형 AI 뉴스레터 제작 및 자동 검수 에이전트 Streamlit 대시보드

실행 방법:
streamlit run streamlit_app.py
"""

import streamlit as st
import time
from datetime import datetime
from agent_graph import workflow_engine

# ==========================================
# 1. Streamlit 페이지 환경 설정 & Apple HIG 커스텀 CSS
# ==========================================
st.set_page_config(
    page_title="AgentLetter Pro — AI 뉴스레터 에이전트",
    page_icon="🍎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apple HIG Glassmorphism & System Font Styling
st.markdown("""
<style>
    /* Pretendard / Apple SF Font */
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "SF Pro Text", sans-serif;
    }
    
    /* Global Card & Head Item Styling */
    .apple-head-card {
        padding: 16px;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.1);
        margin-bottom: 12px;
        transition: all 0.2s ease;
    }
    .apple-head-card:hover {
        border-color: #0A84FF;
        background: rgba(10, 132, 255, 0.05);
    }
    .apple-head-card.active-selected {
        border: 1.5px solid #0A84FF;
        background: rgba(10, 132, 255, 0.08);
        box-shadow: 0 4px 16px rgba(10, 132, 255, 0.15);
    }
    
    /* Badges & Pills */
    .badge-pill {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 600;
        margin-right: 4px;
    }
    .badge-pending { background: rgba(255, 159, 10, 0.18); color: #FF9F0A; border: 1px solid rgba(255, 159, 10, 0.3); }
    .badge-approved { background: rgba(48, 209, 88, 0.18); color: #30D158; border: 1px solid rgba(48, 209, 88, 0.3); }
    .badge-revision { background: rgba(255, 69, 58, 0.18); color: #FF453A; border: 1px solid rgba(255, 69, 58, 0.3); }
    .badge-score { background: rgba(10, 132, 255, 0.18); color: #0A84FF; border: 1px solid rgba(10, 132, 255, 0.3); }
    
    /* Tag Pills */
    .tag-chip {
        display: inline-block;
        padding: 2px 7px;
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 6px;
        font-size: 11px;
        color: #8E8E93;
        margin-right: 4px;
    }
    
    /* Hero Highlights */
    .hero-summary-box {
        background: rgba(10, 132, 255, 0.06);
        border-left: 3px solid #0A84FF;
        padding: 14px 18px;
        border-radius: 0 10px 10px 0;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. Session State 초기화
# ==========================================
if "keywords" not in st.session_state:
    st.session_state.keywords = ["LangGraph", "Human-in-the-Loop", "FastAPI", "AWS EventBridge", "Multi-Agent"]

if "frequency" not in st.session_state:
    st.session_state.frequency = "daily"

if "selected_draft_id" not in st.session_state:
    st.session_state.selected_draft_id = "draft-001"

if "filter_status" not in st.session_state:
    st.session_state.filter_status = "전체"

if "selected_batch_ids" not in st.session_state:
    st.session_state.selected_batch_ids = set(["draft-003"])

if "drafts" not in st.session_state:
    st.session_state.drafts = [
        {
            "id": "draft-001",
            "title": "LangGraph 기반 멀티 에이전트 오케스트레이션과 실무 적용 가이드",
            "summary": "리서치, 작성, 검수 에이전트가 협업하는 순환형 파이프라인 구조와 Conditional Edges를 통한 품질 자동 보정 메커니즘을 심층 분석합니다.",
            "tags": ["LangGraph", "Multi-Agent", "StateCheckpoint"],
            "date": "2026.08.24 08:30",
            "frequency": "daily",
            "status": "pending",
            "score": 96,
            "score_grade": "A+ 우수",
            "author_agent": "작성 에이전트 v2.4 (Claude 3.5 Sonnet)",
            "inspector_agent": "검수 에이전트 v3.1 (GPT-4o)",
            "article_markdown": """
### 💡 이번 호 핵심 요약 (Executive Summary)
단일 프롬프트 기반 생성의 한계를 넘어, **리서치-작성-검수-인간 승인**으로 이어지는 LangGraph 그래프 아키텍처가 엔터프라이즈 생성 파이프라인의 표준으로 자리잡고 있습니다.

---

### 1. 왜 단일 LLM 대신 멀티 에이전트인가?
복잡한 뉴스레터나 전문 리포트를 생성할 때 단일 LLM은 환각(Hallucination)과 맥락 누락의 문제를 겪습니다. LangGraph는 각 에이전트에게 명확한 역할(Role-based)을 부여하고, 상태(State)를 중앙에서 보존(Checkpoint)함으로써 고품질 결과를 보장합니다.

### 2. LangGraph Conditional Edges를 통한 순환 품질 검수
검수 에이전트가 초안의 신뢰도 및 가독성을 진단하여 90점 미만으로 판정할 경우, 그래프는 종료되지 않고 `작성 에이전트` 노드로 되돌아가는 조건부 분기(Conditional Edge)를 실행합니다.

```python
# LangGraph 조건부 엣지 정의 예시
def check_quality_condition(state: NewsletterState):
    if state["review_score"] >= 90:
        return "human_approval"
    return "rewrite_draft"  # 품질 미달 시 순환 복귀

workflow.add_conditional_edges(
    "quality_reviewer",
    check_quality_condition,
    {
        "human_approval": "human_interrupt_node",
        "rewrite_draft": "draft_writer"
    }
)
```

### 3. Human-in-the-loop (인간 승인)의 핵심 가치
에이전트가 아무리 정교해도 최종 발송 전 사람의 맥락적 승인은 필수적입니다. FastAPI의 `interrupt_before` 지점을 통해 생성 작업을 안전하게 일시정지하고, 관리자의 승인이 확인되면 최종 이메일 발송 큐로 전송합니다.
            """,
            "sources": [
                {"title": "LangGraph Multi-Agent Architecture Whitepaper 2026", "domain": "docs.langchain.com", "summary": "멀티 에이전트 상태 전이 제어 및 Human-in-the-loop 체크포인트 설계 공식 가이드"},
                {"title": "Building Reliable Agentic Workflows with Conditional Routing", "domain": "arxiv.org/abs/2602.10982", "summary": "자율 에이전트의 품질 보정을 위한 자동 피드백 루프의 수렴 속도 실증 논문"}
            ],
            "audit_report": {
                "readability": 98,
                "fact_accuracy": 95,
                "coherence": 96,
                "reviewer_comment": "타겟 독자에게 적절한 어조와 명확한 다이어그램 코드 예시가 포함되어 검수를 우수한 성적으로 통과하였습니다.",
                "loop_count": "1회 순환 후 통과 (최초 84점 -> 보완 후 96점)"
            }
        },
        {
            "id": "draft-002",
            "title": "FastAPI와 LangGraph State Checkpoint를 연동한 실시간 HITL 시스템",
            "summary": "FastAPI의 REST API와 웹소켓을 통해 LangGraph의 interrupt_before 이벤트를 브라우저에 실시간 스트리밍하고 승인/반려하는 아키텍처를 소개합니다.",
            "tags": ["FastAPI", "Human-in-the-Loop", "WebSockets"],
            "date": "2026.08.24 07:15",
            "frequency": "daily",
            "status": "pending",
            "score": 93,
            "score_grade": "A 우수",
            "author_agent": "작성 에이전트 v2.4 (Claude 3.5 Sonnet)",
            "inspector_agent": "검수 에이전트 v3.1 (GPT-4o)",
            "article_markdown": """
### 💡 이번 호 핵심 요약 (Executive Summary)
에이전트가 백그라운드에서 작업을 처리하다가 사람이 검토해야 할 시점에 정확히 멈추고(interrupt), 웹 UI에서 원클릭으로 이어받아 실행하는 엔드투엔드 파이프라인 구현법을 다룹니다.

---

### 1. 비동기 인터럽트와 상태 체크포인트의 필요성
AI가 생성한 뉴스레터 초안을 즉시 발송하지 않고 관리자가 웹 UI에서 검토 후 승인할 수 있도록 FastAPI 백엔드는 LangGraph의 `thread_id`를 기반으로 진행 상태를 유지합니다.

### 2. FastAPI 승인/반려 엔드포인트 설계
관리자가 승인 버튼을 누르면 `/api/newsletter/{thread_id}/resume` 엔드포인트가 호출되어 중단되었던 LangGraph 그래프가 발송 노드로 진행됩니다.
            """,
            "sources": [
                {"title": "FastAPI Human-in-the-Loop Integration Recipes", "domain": "github.com/fastapi/hitl-example", "summary": "FastAPI 백그라운드 태스크 및 LangGraph 체크포인트 연동 오픈소스 프로젝트"}
            ],
            "audit_report": {
                "readability": 94,
                "fact_accuracy": 92,
                "coherence": 93,
                "reviewer_comment": "API 엔드포인트 구조 설명이 명확하며, 프론트엔드 연동 관점의 설명이 잘 작성되었습니다.",
                "loop_count": "0회 (초기 작성 즉시 93점 통과)"
            }
        },
        {
            "id": "draft-003",
            "title": "AWS EventBridge & Lambda 기반 정기 뉴스레터 서버리스 발송 자동화",
            "summary": "CloudWatch Events와 EventBridge 크론 스케줄을 통해 매일/매주 정해진 시각에 뉴스레터 에이전트 파이프라인을 구동하고 SES로 대량 발송하는 클라우드 아키텍처.",
            "tags": ["AWS EventBridge", "CloudWatch", "Lambda", "SES"],
            "date": "2026.08.23 18:30",
            "frequency": "weekly",
            "status": "approved",
            "score": 98,
            "score_grade": "A+ 최우수",
            "author_agent": "작성 에이전트 v2.4 (Claude 3.5 Sonnet)",
            "inspector_agent": "검수 에이전트 v3.1 (GPT-4o)",
            "article_markdown": """
### 💡 이번 호 핵심 요약 (Executive Summary)
매일 오전 8시 30분, AWS EventBridge가 람다 트리거를 작동시켜 리서치 에이전트를 깨우고, 생성된 뉴스레터는 사람이 승인하는 즉시 Amazon SES를 통해 수천 명의 구독자에게 1초 만에 발송됩니다.

---

### 1. 서버리스 크론 스케줄러 설계
AWS EventBridge Rule을 활용하여 사용자가 웹 화면에서 설정한 주기(매일, 매주 월/수/금 등)에 맞춰 정확한 타임존(KST)으로 트리거 이벤트를 발행합니다.
            """,
            "sources": [
                {"title": "AWS EventBridge Scheduling Patterns for AI Agents", "domain": "aws.amazon.com/blogs/architecture", "summary": "AWS 공식 아키텍처 블로그: 스케줄링 가이드"}
            ],
            "audit_report": {
                "readability": 99,
                "fact_accuracy": 98,
                "coherence": 97,
                "reviewer_comment": "완벽한 클라우드 아키텍처 다이어그램 및 비용 분석이 포함되어 최고점을 부여하였습니다.",
                "loop_count": "0회 (초기 작성 즉시 98점 통과)"
            }
        }
    ]


# ==========================================
# 3. [사이드바] 1. 입력받는 항목 (Input & Configuration)
# ==========================================
with st.sidebar:
    st.markdown("### 🍎 AgentLetter Pro")
    st.caption("맞춤형 뉴스레터 제작 & 자동 검수 에이전트")
    
    st.markdown("""
    <div style="background: rgba(255, 159, 10, 0.12); padding: 8px 12px; border-radius: 10px; border: 1px solid rgba(255, 159, 10, 0.3); margin-bottom: 16px;">
        <span style="color: #FF9F0A; font-size: 12px; font-weight: 600;">⚡ LangGraph Checkpoint</span><br>
        <span style="font-size: 11px; color: #aeaeb2;">인간 승인 대기 중 (HITL Interrupt)</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("1. 관심 키워드 검색 & 추가")
    
    col_input, col_add = st.columns([3.5, 1.2])
    with col_input:
        new_kw = st.text_input("새 키워드", placeholder="예: RAG, LangChain...", label_visibility="collapsed")
    with col_add:
        if st.button("➕ 추가", use_container_width=True):
            clean_kw = new_kw.strip().replace("#", "")
            if clean_kw and clean_kw not in st.session_state.keywords:
                st.session_state.keywords.append(clean_kw)
                st.toast(f"'{clean_kw}' 키워드가 추가되었습니다!", icon="✅")
                st.rerun()

    # 등록된 키워드 태그 표시
    st.markdown("**현재 구독 키워드:**")
    kw_tags_html = " ".join([f"<span class='tag-chip'>#{k}</span>" for k in st.session_state.keywords])
    st.markdown(kw_tags_html, unsafe_allow_html=True)

    # 핫 토픽 빠른 추가
    st.caption("추천 핫 토픽:")
    hot_cols = st.columns(2)
    with hot_cols[0]:
        if st.button("+ LLM-as-a-Judge", use_container_width=True):
            if "LLM-as-a-Judge" not in st.session_state.keywords:
                st.session_state.keywords.append("LLM-as-a-Judge")
                st.rerun()
    with hot_cols[1]:
        if st.button("+ Serverless SES", use_container_width=True):
            if "Serverless SES" not in st.session_state.keywords:
                st.session_state.keywords.append("Serverless SES")
                st.rerun()

    st.markdown("---")
    st.subheader("2. 발송 및 수집 주기")
    freq_options = ["매일 (Daily)", "주간 (Weekly)", "격주", "월간 (Monthly)"]
    selected_freq_label = st.radio("주기 선택 (Apple Segmented Style)", freq_options, index=0, horizontal=False)
    
    dispatch_time = st.selectbox("발송 시간대", ["오전 07:00 (조간 브리핑)", "오전 08:30 (출근길 요약)", "오후 12:30 (점심 브리핑)", "오후 06:30 (퇴근길 총괄)"], index=1)
    
    if "주간" in selected_freq_label:
        st.multiselect("발송 요일", ["월", "화", "수", "목", "금"], default=["월", "수", "금"])

    st.markdown("---")
    st.subheader("3. 에이전트 파이프라인 정책")
    st.toggle("자동 품질 검수 (Conditional Edge 90점 기준)", value=True)
    st.toggle("인간 승인 일시 중단 (State Checkpoint)", value=True)

    st.markdown("---")
    # 초안 생성 트리거 버튼
    if st.button("🚀 새 뉴스레터 초안 생성 요청", type="primary", use_container_width=True):
        with st.status("LangGraph 멀티 에이전트 파이프라인 가동 중...", expanded=True) as status:
            st.write("🔍 [1/4] 리서치 에이전트: 최신 웹/논문 자료 수집 중...")
            time.sleep(0.8)
            st.write("✍️ [2/4] 작성 에이전트: 뉴스레터 초안 본문 구성 중...")
            time.sleep(0.8)
            st.write("🤖 [3/4] 검수 에이전트: 가독성 & 사실정확도 평가 중...")
            time.sleep(0.8)
            
            # 새 초안 데이터 생성
            new_id = f"draft-{len(st.session_state.drafts) + 1:03d}"
            primary_kw = st.session_state.keywords[0] if st.session_state.keywords else "생성형AI"
            
            new_item = {
                "id": new_id,
                "title": f"{primary_kw} 실무 적용 트렌드 및 최신 아키텍처 2026",
                "summary": f"관심 키워드 #{primary_kw}를 기반으로 리서치 및 검수 에이전트가 방금 생성한 최신 초안입니다.",
                "tags": [primary_kw, "자동생성", "Multi-Agent"],
                "date": datetime.now().strftime("%Y.%m.%d %H:%M"),
                "frequency": "daily",
                "status": "pending",
                "score": 95,
                "score_grade": "A+ 우수",
                "author_agent": "작성 에이전트 v2.4 (Claude 3.5 Sonnet)",
                "inspector_agent": "검수 에이전트 v3.1 (GPT-4o)",
                "article_markdown": f"""
### 💡 이번 호 핵심 요약
#{primary_kw}에 대한 최신 리서치 데이터를 기반으로 자동 생성되었습니다. 검수 점수 기준을 우수하게 통과하여 관리자님의 최종 검토를 기다리고 있습니다.

---

### 1. 주요 아키텍처 동향
산업 전반에서 #{primary_kw} 도입이 활발해지면서, 신뢰성과 개발 생산성을 극대화하기 위한 멀티 에이전트 파이프라인이 필수 표준으로 자리잡았습니다.

### 2. 실무 체크포인트
FastAPI 비동기 웹훅과 상태 체크포인트를 결합하여 병목을 없애고 안정성을 유지하세요.
                """,
                "sources": [
                    {"title": f"{primary_kw} 2026 Emerging Trends", "domain": "techinsights.io", "summary": f"{primary_kw} 최신 연구 자료"}
                ],
                "audit_report": {
                    "readability": 96,
                    "fact_accuracy": 94,
                    "coherence": 95,
                    "reviewer_comment": "품질 검수 기준(90점 이상)을 만족하여 인간 승인 대기 상태로 전달되었습니다.",
                    "loop_count": "0회 (1차 통과)"
                }
            }
            st.session_state.drafts.insert(0, new_item)
            st.session_state.selected_draft_id = new_id
            status.update(label="✅ [4/4] 뉴스레터 생성 완료 (승인 대기 중)", state="complete")
        st.toast("새 뉴스레터 초안이 성공적으로 생성되었습니다!", icon="🎉")
        st.rerun()


# ==========================================
# 4. 메인 화면 2단 분할 (Master List & Detail View)
# ==========================================
col_master, col_detail = st.columns([4.2, 5.8], gap="large")

# -------------------------------------------------------------
# [중앙] 2. 백엔드 출력 헤드 목록 (Draft Head List)
# -------------------------------------------------------------
with col_master:
    st.markdown("### 📑 뉴스레터 초안 헤드 목록")
    st.caption("백엔드 에이전트가 생성한 초안 목록입니다. 헤드를 클릭하여 상세 검수 및 승인을 진행하세요.")
    
    # 필터 컨트롤
    filter_opts = ["전체", "승인 대기", "승인 완료", "수정 중"]
    selected_filter = st.segmented_control("상태 필터", filter_opts, default="전체")
    
    status_map = {"승인 대기": "pending", "승인 완료": "approved", "수정 중": "revision"}
    
    filtered_drafts = [
        d for d in st.session_state.drafts
        if selected_filter == "전체" or d["status"] == status_map.get(selected_filter)
    ]
    
    st.markdown(f"**총 {len(filtered_drafts)}건의 초안**")

    # 일괄 승인 버튼
    if st.button("✓ 선택 항목 일괄 승인", use_container_width=True):
        if st.session_state.selected_batch_ids:
            for d in st.session_state.drafts:
                if d["id"] in st.session_state.selected_batch_ids:
                    d["status"] = "approved"
            st.toast(f"{len(st.session_state.selected_batch_ids)}건의 뉴스레터가 일괄 승인되었습니다!", icon="🎉")
            st.rerun()

    # 헤드 목록 카드 렌더링
    for draft in filtered_drafts:
        is_selected = draft["id"] == st.session_state.selected_draft_id
        is_checked = draft["id"] in st.session_state.selected_batch_ids
        
        status_badge = {
            "pending": "<span class='badge-pill badge-pending'>● 승인 대기</span>",
            "approved": "<span class='badge-pill badge-approved'>✓ 발송 완료</span>",
            "revision": "<span class='badge-pill badge-revision'>↻ 수정 중</span>"
        }.get(draft["status"], "")
        
        card_class = "apple-head-card active-selected" if is_selected else "apple-head-card"
        
        with st.container():
            st.markdown(f"""
            <div class="{card_class}">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div style="font-weight: 700; font-size: 14px; color: #f5f5f7; line-height: 1.3;">{draft['title']}</div>
                </div>
                <div style="font-size: 12px; color: #8e8e93; margin: 6px 0 10px 0; line-height: 1.4;">
                    {draft['summary']}
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        {' '.join([f"<span class='tag-chip'>#{t}</span>" for t in draft['tags'][:2]])}
                    </div>
                    <div>
                        <span class='badge-pill badge-score'>{draft['score']}점</span>
                        {status_badge}
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            btn_col1, btn_col2 = st.columns([1, 4])
            with btn_col1:
                batch_check = st.checkbox("선택", value=is_checked, key=f"chk_{draft['id']}")
                if batch_check:
                    st.session_state.selected_batch_ids.add(draft["id"])
                else:
                    st.session_state.selected_batch_ids.discard(draft["id"])
            with btn_col2:
                if st.button("🔍 상세 검수 및 승인", key=f"btn_{draft['id']}", use_container_width=True):
                    st.session_state.selected_draft_id = draft["id"]
                    st.rerun()


# -------------------------------------------------------------
# [우측] 3. 상세 보기 및 최종 승인 (Detail & Human-in-the-Loop)
# -------------------------------------------------------------
with col_detail:
    current_draft = next((d for d in st.session_state.drafts if d["id"] == st.session_state.selected_draft_id), None)
    
    if current_draft:
        # 상단 헤더
        st.markdown(f"### {current_draft['title']}")
        
        meta_col1, meta_col2 = st.columns([3, 1.2])
        with meta_col1:
            st.caption(f"📅 생성 일시: {current_draft['date']}  |  ✍️ {current_draft['author_agent']}")
            st.markdown(" ".join([f"<span class='tag-chip'>#{t}</span>" for t in current_draft['tags']]), unsafe_allow_html=True)
        with meta_col2:
            st.metric("검수 점수", f"{current_draft['score']}점", current_draft['score_grade'])

        st.markdown("---")

        # 3대 탭 구성
        tab1, tab2, tab3 = st.tabs(["📰 뉴스레터 본문 전문", "🔍 리서치 수집 근거", "🤖 검수 에이전트 진단표"])
        
        with tab1:
            st.markdown(current_draft["article_markdown"])
            
        with tab2:
            st.markdown("#### 🌐 리서치 에이전트가 수집한 웹/문헌 출처")
            for src in current_draft.get("sources", []):
                st.markdown(f"""
                <div style="background: rgba(255, 255, 255, 0.04); padding: 12px; border-radius: 10px; margin-bottom: 8px; border: 1px solid rgba(255, 255, 255, 0.08);">
                    <div style="font-weight: 600; color: #0A84FF; font-size: 13px;">🔗 {src['title']}</div>
                    <div style="font-size: 11px; color: #8e8e93;">출처: {src['domain']}</div>
                    <div style="font-size: 12px; color: #d1d1d6; margin-top: 4px;">{src['summary']}</div>
                </div>
                """, unsafe_allow_html=True)
                
        with tab3:
            st.markdown("#### 📊 LLM-as-a-Judge 품질 감사 리포트")
            audit = current_draft.get("audit_report", {"readability": 95, "fact_accuracy": 95, "coherence": 95, "reviewer_comment": "양호", "loop_count": "0회"})
            
            m1, m2, m3 = st.columns(3)
            m1.progress(audit["readability"] / 100, text=f"가독성: {audit['readability']}점")
            m2.progress(audit["fact_accuracy"] / 100, text=f"사실 정확도: {audit['fact_accuracy']}점")
            m3.progress(audit["coherence"] / 100, text=f"주제 일관성: {audit['coherence']}점")
            
            st.info(f"**🤖 검수 에이전트 총평:** {audit['reviewer_comment']}")
            st.caption(f"⚡ **LangGraph 조건부 순환 이력:** {audit['loop_count']}")

        st.markdown("---")

        # =========================================================
        # 4. Human-in-the-Loop 최종 액션 바
        # =========================================================
        st.markdown("#### ⏸️ Human-in-the-Loop 최종 승인 액션")
        st.caption("FastAPI `interrupt_before` 체크포인트에 도달하여 승인 전까지 발송이 보류되어 있습니다.")

        action_col1, action_col2 = st.columns(2)
        
        with action_col1:
            with st.expander("🔴 수정 요청 (작성 에이전트 재작성 루프)"):
                feedback_txt = st.text_area("보완 요청 피드백", placeholder="예: 'AWS 배포 부분 아키텍처 다이어그램 설명을 보강해주세요.'")
                if st.button("수정 피드백 전송 (Conditional Loop)", type="secondary", use_container_width=True):
                    if feedback_txt.strip():
                        current_draft["status"] = "revision"
                        current_draft["audit_report"]["loop_count"] = f"피드백 반영 중: '{feedback_txt[:20]}...'"
                        st.toast("작성 에이전트로 피드백이 전송되어 초안을 재작성합니다.", icon="↻")
                        time.sleep(1.0)
                        current_draft["status"] = "pending"
                        current_draft["score"] = 98
                        current_draft["score_grade"] = "A+ 우수 (수정 완료)"
                        current_draft["audit_report"]["reviewer_comment"] = f"피드백('{feedback_txt[:15]}...')이 반영되어 재검수를 통과했습니다."
                        current_draft["article_markdown"] += f"\n\n> **✨ 피드백 반영 완료:** {feedback_txt}"
                        st.rerun()
                    else:
                        st.warning("수정 요청 내용을 입력해주세요.")

        with action_col2:
            if current_draft["status"] == "approved":
                st.button("✅ 이미 발송 승인 완료됨", disabled=True, use_container_width=True)
            else:
                if st.button("🟢 최종 승인 및 발송 확정", type="primary", use_container_width=True):
                    current_draft["status"] = "approved"
                    st.balloons()
                    st.toast(f"'{current_draft['title']}' 뉴스레터가 최종 승인되어 AWS EventBridge 큐로 발송되었습니다!", icon="🎉")
                    st.rerun()
    else:
        st.info("왼쪽 목록에서 검토할 뉴스레터 헤드 카드를 선택하세요.")
