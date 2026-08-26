"""
streamlit_app.py
AgentLetter Compact UI v3

외부 스타일 참조:
- @import url('https://mulcam.1435.co.kr/docs')
- 외부 URL이 CSS를 반환하지 않아도 시스템 폰트/CSS fallback으로 화면 유지

PowerPoint '화면수정-3' 요청 반영:
- 빨간 박스 영역 숨김: 섹션 제목/설명/헤드 선택 multiselect, 상세 내용/검수 expander 제거
- 파란 박스 영역 통합: '왜 마음에 안 드나요?' + '어떻게 바꿔 주세요?' -> '이렇게 바꾸어주세요' 1개 입력창
- 초록 박스 '주기' 이동: 뉴스레터 요청 영역에서 제거하고 '최종 승인' 버튼 옆으로 이동
- 선택한 뉴스의 헤드 카드는 compact하게 그대로 표시

실행:
python -m streamlit run streamlit_app.py
"""

import html
import re
from datetime import datetime

import streamlit as st

import backend_client as backend


# ---------------------------------------------------------
# 1. 페이지 설정 / Compact CSS
# ---------------------------------------------------------
st.set_page_config(
    page_title="AgentLetter Compact",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      /*
       * 외부 스타일 참조 URL
       * /docs가 CSS가 아닌 HTML/Swagger 문서를 반환하더라도
       * 아래 자체 스타일과 시스템 폰트 fallback으로 화면은 정상 동작합니다.
       */
      @import url("https://mulcam.1435.co.kr/docs");

      :root {
          --app-font: -apple-system, BlinkMacSystemFont, "Segoe UI",
                      "Apple SD Gothic Neo", "Malgun Gothic", Arial, sans-serif;
          --card-radius: 12px;
          --card-border: rgba(128,128,128,.25);
          --muted-opacity: .72;
      }

      html, body, [class*="st-"], [data-testid="stAppViewContainer"] {
          font-family: var(--app-font) !important;
      }

      .block-container {
          padding-top: 1.0rem;
          padding-bottom: 1.0rem;
          max-width: 1180px;
      }
      h1, h2, h3 { margin-bottom: .3rem !important; }
      div[data-testid="stTextArea"] textarea { min-height: 92px; }
      .compact-card {
          border: 1px solid rgba(128,128,128,.25);
          border-radius: var(--card-radius);
          padding: 13px 15px;
          margin: 8px 0 2px 0;
          background: rgba(128,128,128,.035);
      }
      .head-title {
          font-size: 15px;
          font-weight: 700;
          line-height: 1.35;
          margin-bottom: 5px;
      }
      .head-summary {
          font-size: 12.5px;
          opacity: .80;
          line-height: 1.5;
      }
      .head-meta {
          font-size: 11px;
          opacity: .65;
          margin-top: 7px;
      }
      .flow {
          font-size: 12px;
          opacity: var(--muted-opacity);
          margin-top: -4px;
          margin-bottom: 8px;
      }
      .section-label {
          font-weight: 700;
          font-size: 16px;
          margin-bottom: 2px;
      }
      div[data-testid="stVerticalBlockBorderWrapper"] {
          border-radius: var(--card-radius);
      }
      /* 상단 두 박스 사이 간격을 조금 줄임 */
      div[data-testid="stHorizontalBlock"] { gap: .8rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# 2. 보조 함수
# ---------------------------------------------------------
def extract_keywords(request_text: str):
    """자유형 요청 문장에서 Agent 입력용 핵심 키워드 1~4개를 간단히 추출."""
    direct = [
        p.strip()
        for p in re.split(r"[,/#\n]+", request_text)
        if p.strip()
    ]
    if len(direct) >= 2:
        return direct[:4]

    words = re.findall(r"[가-힣A-Za-z0-9.+-]+", request_text)
    stop_words = {
        "뉴스", "뉴스레터", "관련", "대해", "대한", "만들어", "작성", "해줘",
        "해주세요", "알려줘", "최근", "최신", "내용", "중심으로", "보고", "정리",
    }
    result = []
    for word in words:
        if len(word) < 2 or word in stop_words:
            continue
        if word not in result:
            result.append(word)
        if len(result) == 4:
            break
    return result or ["AI"]


def short_status(status: str):
    return {
        "pending": "승인 대기",
        "approved": "승인 완료",
        "revision": "수정 중",
    }.get(status, status)


def find_draft(draft_id: str):
    return next(
        (d for d in st.session_state.drafts if d["id"] == draft_id),
        None,
    )


def replace_draft(updated):
    for i, draft in enumerate(st.session_state.drafts):
        if draft["id"] == updated["id"]:
            st.session_state.drafts[i] = updated
            return
    st.session_state.drafts.insert(0, updated)


def frequency_label(value: str):
    return {
        "daily": "매일",
        "weekly": "주간",
        "monthly": "월간",
    }.get(value, value)


# ---------------------------------------------------------
# 3. Session State 초기화
# ---------------------------------------------------------
if "frequency" not in st.session_state:
    st.session_state.frequency = "daily"

if "drafts" not in st.session_state:
    # 백엔드에 이미 만들어 둔 요약본이 있으면 가져온다.
    # 없으면 빈 목록으로 시작한다 (가짜 샘플을 만들지 않는다).
    try:
        st.session_state.drafts = backend.list_drafts()
    except Exception:
        st.session_state.drafts = []

if "active_draft_id" not in st.session_state:
    st.session_state.active_draft_id = (
        st.session_state.drafts[0]["id"] if st.session_state.drafts else None
    )

if "advice" not in st.session_state:
    st.session_state.advice = None

# 추천 요청문을 눌렀을 때는 다음 실행에서 입력칸에 채운다.
# (Streamlit 은 위젯이 그려진 뒤에 그 키를 바꿀 수 없다)
if st.session_state.get("pending_request"):
    st.session_state.newsletter_request_input = st.session_state.pop("pending_request")

if "last_request" not in st.session_state:
    st.session_state.last_request = ""


# ---------------------------------------------------------
# 4. 상단 Header
# ---------------------------------------------------------
st.markdown("## 📰 AgentLetter Compact")
st.markdown(
    '<div class="flow">Research → Writer → Reviewer → ⏸ Human Approval → Send</div>',
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# 5. 상단 Compact 입력 영역
# ---------------------------------------------------------
input1_col, input2_col = st.columns([1, 1], gap="medium")

# 입력항목 1 - 뉴스레터 요청
with input1_col:
    with st.container(border=True):
        st.markdown(
            '<div class="section-label">① 뉴스레터 요청</div>',
            unsafe_allow_html=True,
        )

        newsletter_request = st.text_area(
            "원하는 뉴스레터 내용을 입력하세요.",
            placeholder=(
                "예: 생성형 AI와 LangGraph의 이번 주 주요 뉴스를 "
                "실무자 관점에서 5개 정도 정리해 주세요."
            ),
            key="newsletter_request_input",
        )

        # PPT 요청: '주기'는 이 영역에서 제거
        # 초보자 도우미 — 무엇을 적어야 할지 모를 때 되물어 준다
        help_col, gen_col = st.columns([1, 1.6], gap="small")
        with help_col:
            ask_help = st.button("💡 뭘 적을지 모르겠어요", use_container_width=True)
        with gen_col:
            generate = st.button(
                "🚀 뉴스레터 요청",
                type="primary",
                use_container_width=True,
            )

        if ask_help:
            if not newsletter_request.strip():
                st.warning("먼저 관심 있는 주제를 한 단어라도 적어 주세요. 예) 로봇")
            else:
                with st.spinner("편집장이 되묻는 중"):
                    try:
                        st.session_state.advice = backend.advise(
                            newsletter_request.strip()
                        )
                    except backend.BackendError as e:
                        st.error(str(e))

        # 되묻기 결과 표시
        adv = st.session_state.get("advice")
        if adv:
            st.markdown("**이런 점을 정해 보시면 좋습니다**")
            for q in adv.get("questions", []):
                st.markdown(f"- {q}")

            st.markdown("**그대로 눌러 쓰셔도 됩니다**")
            for i, sug in enumerate(adv.get("suggestions", [])):
                if st.button(sug, key=f"sug_{i}", use_container_width=True):
                    st.session_state.pending_request = sug
                    st.session_state.advice = None
                    st.rerun()

            if adv.get("note"):
                st.caption(adv["note"])

        if generate:
            if not newsletter_request.strip():
                st.warning("뉴스레터 요청 내용을 입력해 주세요.")
            else:
                new_id = f"draft-{datetime.now().strftime('%H%M%S%f')}"
                keywords = extract_keywords(newsletter_request)

                with st.status(
                    "Research → Writer → Reviewer 실행 중 (10~20초)",
                    expanded=False,
                ) as status:
                    try:
                        new_draft = backend.create(newsletter_request.strip())
                        status.update(
                            label=f"✅ 생성 완료 · 검수 {new_draft['score']}점 · 인간 승인 대기",
                            state="complete",
                        )
                    except backend.BackendError as e:
                        status.update(label="❌ 생성 실패", state="error")
                        st.error(str(e))
                        new_draft = None

                if new_draft:
                    st.session_state.drafts.insert(0, new_draft)
                    st.session_state.active_draft_id = new_draft["id"]
                    st.session_state.last_request = newsletter_request.strip()
                    st.session_state.advice = None
                    st.rerun()


# 입력항목 2 - 수정 요청 / 최종 승인 / 주기
with input2_col:
    with st.container(border=True):
        st.markdown(
            '<div class="section-label">② 마음에 안 들 경우 — 수정 요청</div>',
            unsafe_allow_html=True,
        )

        draft_options_for_feedback = [d["id"] for d in st.session_state.drafts]
        feedback_title_map = {
            d["id"]: d["title"] for d in st.session_state.drafts
        }

        if draft_options_for_feedback:
            if st.session_state.active_draft_id not in draft_options_for_feedback:
                st.session_state.active_draft_id = draft_options_for_feedback[0]

            active_index = draft_options_for_feedback.index(
                st.session_state.active_draft_id
            )
            target_id = st.selectbox(
                "수정/승인 대상 뉴스",
                draft_options_for_feedback,
                index=active_index,
                format_func=lambda draft_id: feedback_title_map[draft_id],
            )
            st.session_state.active_draft_id = target_id
        else:
            st.selectbox(
                "수정/승인 대상 뉴스",
                ["— 아직 만들어진 뉴스레터가 없습니다 —"],
                disabled=True,
            )

        # PPT 요청: 파란 박스의 두 입력창을 하나로 합침
        change_request = st.text_area(
            "이렇게 바꾸어주세요",
            placeholder=(
                "예: 너무 기술적인 표현은 줄이고, 핵심 뉴스 5개를 먼저 보여준 뒤 "
                "각 항목을 실무자가 이해하기 쉽게 설명해 주세요."
            ),
            key="change_request_combined",
        )

        active = find_draft(st.session_state.active_draft_id)

        # PPT 요청: '주기'를 '최종 승인' 옆으로 이동
        action1, action2, action3 = st.columns([1.0, 1.15, 0.9])
        with action1:
            revise = st.button(
                "↻ 수정 요청",
                use_container_width=True,
                disabled=active is None,
            )
        with action2:
            approve = st.button(
                "✅ 최종 승인",
                type="primary",
                use_container_width=True,
                disabled=active is None or active.get("status") == "approved",
            )
        with action3:
            selected_frequency = st.selectbox(
                "주기",
                ["daily", "weekly", "monthly"],
                index=["daily", "weekly", "monthly"].index(st.session_state.frequency),
                format_func=frequency_label,
                key="frequency_select",
            )
            st.session_state.frequency = selected_frequency

        if revise and active:
            if not change_request.strip():
                st.warning("'이렇게 바꾸어주세요'에 수정 요청 내용을 입력해 주세요.")
            else:
                with st.spinner("Writer → Reviewer 재실행 중 (10~20초)"):
                    try:
                        updated = backend.revise(active["id"], change_request.strip())
                        updated["frequency"] = st.session_state.frequency
                        replace_draft(updated)
                        st.session_state.active_draft_id = updated["id"]
                        st.success(
                            f"다시 작성했습니다. 검수 {updated['score']}점 "
                            f"(수정 {updated.get('revision_count', 0)}회)"
                        )
                        st.rerun()
                    except backend.BackendError as e:
                        st.error(str(e))

        if approve and active:
            with st.spinner("승인 처리 및 발송 중"):
                try:
                    updated = backend.approve(active["id"], st.session_state.frequency)
                    replace_draft(updated)

                    sent = updated.get("send_result") or {}
                    if sent.get("sent"):
                        st.success(
                            f"최종 승인 후 {sent.get('count', 0)}명에게 발송했습니다. "
                            f"주기: {frequency_label(st.session_state.frequency)}"
                        )
                    elif sent.get("dry_run"):
                        st.success(
                            f"최종 승인되었습니다. 주기: "
                            f"{frequency_label(st.session_state.frequency)}"
                        )
                        st.caption("발송 안전장치가 켜져 있어 메일은 나가지 않았습니다.")
                    else:
                        st.warning(
                            "승인은 되었으나 발송에 실패했습니다: "
                            + str(sent.get("reason", ""))
                        )
                    st.rerun()
                except backend.BackendError as e:
                    st.error(str(e))


# ---------------------------------------------------------
# 6. 선택 뉴스 헤드 카드만 표시
#    PPT 빨간 박스 요청:
#    - '③ 선택했던 뉴스들의 헤드 내용' 제목/설명 숨김
#    - '출력할 뉴스 헤드 선택' multiselect 숨김
#    - '선택 뉴스의 상세 내용 / 검수 결과' expander 숨김
# ---------------------------------------------------------
active = find_draft(st.session_state.active_draft_id)
if active:
    safe_title = html.escape(str(active.get("title", "")))
    safe_summary = html.escape(str(active.get("summary", "")))
    safe_date = html.escape(str(active.get("date", "")))
    safe_frequency = html.escape(frequency_label(str(active.get("frequency", "daily"))))
    safe_status = html.escape(short_status(str(active.get("status", ""))))

    st.markdown(
        f"""
        <div class="compact-card">
          <div class="head-title">{safe_title}</div>
          <div class="head-summary">{safe_summary}</div>
          <div class="head-meta">
            검수 {active.get('score', '-')}점 · {safe_status} · 주기 {safe_frequency} · {safe_date}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.caption(backend.health_line())
