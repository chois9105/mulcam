"""
streamlit_app.py
Newsletter Frontend - Remote Backend API 연동 버전

구조
----
브라우저
  ↓
Streamlit Frontend (localhost:8501)
  ↓ HTTPS
Remote Newsletter Agent API (https://mulcam.1435.co.kr)

연동 API
--------
POST /api/newsletter/request
POST /api/drafts/{draft_id}/revise
POST /api/drafts/{draft_id}/approve

조회 API
--------
GET /api/drafts
GET /api/drafts/{draft_id}
GET /api/status

중요
----
- 이 파일은 agent_graph.py를 import하지 않습니다.
- 로컬 LangGraph/Agent를 실행하지 않습니다.
- /docs는 Swagger 문서 URL이며 API 호출 Base URL은 https://mulcam.1435.co.kr 입니다.
- 요청 본문은 같은 저장소의 Backend API 계약에 맞춰 고정합니다.
"""

import os
import html
import re
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st

from api_contract import approval_body, newsletter_request_body, revision_body


# ============================================================
# 1. 환경 설정
# ============================================================
BACKEND_BASE_URL = os.getenv(
    "NEWSLETTER_BACKEND_URL",
    "https://mulcam.1435.co.kr"
).rstrip("/")

DOCS_URL = f"{BACKEND_BASE_URL}/docs"
OPENAPI_URL = f"{BACKEND_BASE_URL}/openapi.json"

REQUEST_TIMEOUT = (6, 180)
FREQUENCY_OPTIONS = ["every_30_minutes", "hourly", "daily", "weekly"]


# ============================================================
# 2. 페이지 설정 / Compact UI CSS
# ============================================================
st.set_page_config(
    page_title="Newsletter Frontend",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      :root {
          --app-font: -apple-system, BlinkMacSystemFont, "Segoe UI",
                      "Apple SD Gothic Neo", "Malgun Gothic", Arial, sans-serif;
          --card-radius: 12px;
          --muted-opacity: .72;
      }

      html, body, [class*="st-"], [data-testid="stAppViewContainer"] {
          font-family: var(--app-font) !important;
      }

      /* Streamlit 기본 Deploy/메뉴 헤더를 사용하지 않는다. */
      header[data-testid="stHeader"],
      [data-testid="stToolbar"],
      [data-testid="stDecoration"],
      #MainMenu {
          display: none !important;
      }

      .block-container {
          padding-top: .85rem;
          padding-bottom: 1rem;
          max-width: 1180px;
      }

      h1, h2, h3 {
          margin-bottom: .3rem !important;
      }

      div[data-testid="stTextArea"] textarea {
          min-height: 92px;
      }

      div[data-testid="stVerticalBlockBorderWrapper"] {
          border-radius: var(--card-radius);
      }

      div[data-testid="stHorizontalBlock"] {
          gap: .8rem;
      }

      .section-label {
          font-weight: 700;
          font-size: 16px;
          margin-bottom: 2px;
      }

      .flow {
          font-size: 12px;
          opacity: var(--muted-opacity);
          margin-top: -4px;
          margin-bottom: 8px;
      }

      .compact-card {
          border: 1px solid rgba(128,128,128,.25);
          border-radius: var(--card-radius);
          padding: 13px 15px;
          margin: 8px 0 2px 0;
          background: rgba(128,128,128,.035);
      }

      .compact-card.selected {
          border: 1.5px solid #0A84FF;
          background: rgba(10,132,255,.055);
      }

      .head-title {
          font-size: 15px;
          font-weight: 700;
          line-height: 1.35;
          margin-bottom: 5px;
      }

      .head-summary {
          font-size: 12.5px;
          opacity: .82;
          line-height: 1.5;
      }

      .head-meta {
          font-size: 11px;
          opacity: .66;
          margin-top: 7px;
      }

      .backend-line {
          font-size: 11.5px;
          opacity: .76;
          margin-top: -4px;
          margin-bottom: 10px;
      }

      .newsletter-preview {
          border: 1px solid #E5E7EB;
          border-radius: 12px;
          padding: 24px 26px;
          margin-top: 10px;
          background: #FFFFFF;
          color: #1F2328;
          font-size: 14.5px;
          line-height: 1.75;
      }

      .newsletter-preview h1 {
          color: #1F2328;
          font-size: 22px;
          line-height: 1.4;
          margin: 22px 0 14px !important;
      }

      .newsletter-preview h2,
      .newsletter-preview h3 {
          color: #1F2328;
          margin-top: 20px !important;
      }

      .newsletter-preview p {
          color: #5B6470;
          margin: 0 0 15px;
      }

      .newsletter-preview a {
          color: #E8453C;
          text-decoration: none;
      }

      .newsletter-preview a:hover {
          text-decoration: underline;
      }

      .newsletter-preview .article-hero-box {
          background: #FFF6F5;
          border-left: 4px solid #E8453C;
          border-radius: 0 10px 10px 0;
          padding: 17px 20px;
          margin-bottom: 22px;
      }

      .newsletter-preview .article-hero-title,
      .newsletter-preview .takeaways-title {
          color: #1F2328;
          font-size: 15px;
          font-weight: 700;
          margin-bottom: 7px;
      }

      .newsletter-preview .article-hero-text {
          color: #5B6470;
      }

      .newsletter-preview .article-key-takeaways {
          border-top: 1px solid #E5E7EB;
          margin-top: 24px;
          padding-top: 18px;
      }

      .newsletter-preview .takeaway-list {
          margin: 9px 0 0;
          padding-left: 22px;
      }

      .newsletter-preview .takeaway-list li {
          margin-bottom: 8px;
      }

      .newsletter-preview .source-name {
          color: #9AA1AB;
          font-size: 12.5px;
      }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 3. Backend API 예외 / HTTP 공통 함수
# ============================================================
class BackendAPIError(RuntimeError):
    """원격 Backend API 호출 실패."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


@st.cache_resource
def get_http_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Newsletter-Streamlit-Frontend/1.0",
    })
    return session


def api_request(
    method: str,
    path: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    timeout=REQUEST_TIMEOUT,
) -> Any:
    """원격 Backend에 1회 요청하고 JSON 결과를 반환."""
    url = f"{BACKEND_BASE_URL}{path}"
    session = get_http_session()

    try:
        response = session.request(
            method=method.upper(),
            url=url,
            json=json_body,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise BackendAPIError(
            f"백엔드 서버에 연결할 수 없습니다: {exc}"
        ) from exc

    try:
        payload = response.json()
    except ValueError:
        payload = response.text

    if not response.ok:
        raise BackendAPIError(
            f"{method.upper()} {path} 호출 실패",
            status_code=response.status_code,
            detail=payload,
        )

    return payload


# ============================================================
# 4. OpenAPI Request Body 자동 인식
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def get_openapi_spec() -> Optional[Dict[str, Any]]:
    """
    FastAPI의 /openapi.json을 읽는다.
    읽지 못해도 UI 자체는 동작하며 fallback payload를 사용한다.
    """
    try:
        response = requests.get(
            OPENAPI_URL,
            timeout=(5, 15),
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def resolve_ref(spec: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    """#/components/schemas/... 형태의 $ref를 해석."""
    seen = set()
    current = schema or {}

    while isinstance(current, dict) and "$ref" in current:
        ref = current["$ref"]
        if ref in seen or not ref.startswith("#/"):
            break
        seen.add(ref)

        node: Any = spec
        for part in ref[2:].split("/"):
            if not isinstance(node, dict) or part not in node:
                return current
            node = node[part]
        current = node

    # allOf 한 개짜리 흔한 FastAPI 패턴
    if isinstance(current, dict) and "allOf" in current and len(current["allOf"]) == 1:
        return resolve_ref(spec, current["allOf"][0])

    return current if isinstance(current, dict) else {}


def request_schema(path: str, method: str = "post") -> Optional[Dict[str, Any]]:
    spec = get_openapi_spec()
    if not spec:
        return None

    try:
        operation = spec["paths"][path][method.lower()]
        request_body = operation.get("requestBody")
        if not request_body:
            return {}

        content = request_body.get("content", {})
        media = (
            content.get("application/json")
            or content.get("application/*+json")
            or next(iter(content.values()), {})
        )
        schema = media.get("schema", {})
        return resolve_ref(spec, schema)
    except Exception:
        return None


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]", "", value.lower())


ALIASES = {
    "request_text": [
        "request_text", "request", "newsletter_request", "user_request",
        "prompt", "query", "topic", "content", "text", "instruction",
        "요청", "뉴스레터요청",
    ],
    "feedback": [
        "direction", "feedback", "change_request", "revision_request", "revision",
        "revise", "request_text", "request", "reason", "instruction",
        "content", "text", "수정요청", "피드백",
    ],
    "frequency": [
        "frequency", "period", "cycle", "interval", "schedule",
        "dispatch_frequency", "send_frequency", "주기", "발송주기",
    ],
    "approved": [
        "approved", "approve", "is_approved", "approval", "승인",
    ],
    "approved_template": [
        "approved_template", "template", "article_html", "승인템플릿",
    ],
}


def prop_text(name: str, spec: Dict[str, Any]) -> str:
    parts = [
        name,
        str(spec.get("title", "")),
        str(spec.get("description", "")),
    ]
    return normalize_name(" ".join(parts))


def choose_property(
    properties: Dict[str, Dict[str, Any]],
    logical_name: str,
) -> Optional[str]:
    """논리 필드(request_text/feedback/frequency...)와 실제 OpenAPI 필드를 매핑."""
    aliases = [normalize_name(x) for x in ALIASES[logical_name]]

    # 1) 실제 필드명 정확/부분 일치
    for prop in properties:
        normalized = normalize_name(prop)
        if normalized in aliases:
            return prop

    for prop in properties:
        normalized = normalize_name(prop)
        if any(alias in normalized or normalized in alias for alias in aliases):
            return prop

    # 2) title/description까지 검사
    for prop, spec in properties.items():
        text = prop_text(prop, spec)
        if any(alias and alias in text for alias in aliases):
            return prop

    return None


def value_for_required_property(
    prop_name: str,
    prop_spec: Dict[str, Any],
    *,
    request_text: Optional[str] = None,
    feedback: Optional[str] = None,
    frequency: Optional[str] = None,
) -> Any:
    """필수 필드 중 아직 매핑되지 않은 값에 합리적 기본값을 적용."""
    if "default" in prop_spec:
        return prop_spec["default"]

    if "example" in prop_spec:
        return prop_spec["example"]

    enum = prop_spec.get("enum")
    if enum:
        if frequency in enum:
            return frequency
        return enum[0]

    typ = prop_spec.get("type")

    if typ == "boolean":
        return True

    if typ == "array":
        item_type = (prop_spec.get("items") or {}).get("type")
        if item_type == "string":
            base = request_text or feedback or ""
            return [base] if base else []
        return []

    if typ in ("integer", "number"):
        return 1

    # 문자열 필수 필드는 endpoint 문맥상 사용자가 입력한 텍스트 우선
    if typ in ("string", None):
        return request_text or feedback or frequency or ""

    return None


def build_json_body(
    path: str,
    *,
    request_text: Optional[str] = None,
    feedback: Optional[str] = None,
    frequency: Optional[str] = None,
    approved: Optional[bool] = None,
    approved_template: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    OpenAPI 스키마에 맞춰 JSON Body를 만든다.
    requestBody가 없는 endpoint면 None을 반환한다.
    OpenAPI 접근 실패 시 관례적인 필드명으로 fallback한다.
    """
    schema = request_schema(path, "post")

    # OpenAPI를 못 읽은 경우 안전한 관례적 fallback
    if schema is None:
        if path == "/api/newsletter/request":
            return {"request_text": request_text or ""}
        if path.endswith("/revise"):
            return {"direction": feedback or ""}
        if path.endswith("/approve"):
            return {
                "frequency": frequency or "daily",
                "approved_template": approved_template,
            }
        return {}

    # Request Body 자체가 없는 API
    if schema == {}:
        return None

    properties = schema.get("properties", {})
    required = schema.get("required", [])

    # object schema가 아니면 conventional fallback
    if not properties:
        if path == "/api/newsletter/request":
            return {"request_text": request_text or ""}
        if path.endswith("/revise"):
            return {"direction": feedback or ""}
        if path.endswith("/approve"):
            return {
                "frequency": frequency or "daily",
                "approved_template": approved_template,
            }
        return {}

    body: Dict[str, Any] = {}

    logical_values = {
        "request_text": request_text,
        "feedback": feedback,
        "frequency": frequency,
        "approved": approved,
        "approved_template": approved_template,
    }

    for logical_name, value in logical_values.items():
        if value is None:
            continue

        prop = choose_property(properties, logical_name)
        if prop and prop not in body:
            body[prop] = value

    # 아직 채워지지 않은 required 필드 처리
    for prop in required:
        if prop in body:
            continue
        prop_spec = resolve_ref(get_openapi_spec() or {}, properties.get(prop, {}))
        body[prop] = value_for_required_property(
            prop,
            prop_spec,
            request_text=request_text,
            feedback=feedback,
            frequency=frequency,
        )

    return body


# ============================================================
# 5. Newsletter API 기능
# ============================================================
def backend_status() -> Any:
    return api_request("GET", "/api/status")


def list_drafts_raw() -> Any:
    return api_request("GET", "/api/drafts")


def get_draft_raw(draft_id: str) -> Any:
    return api_request("GET", f"/api/drafts/{draft_id}")


def request_newsletter(request_text: str) -> Any:
    path = "/api/newsletter/request"
    body = newsletter_request_body(request_text)
    return api_request("POST", path, json_body=body)


def revise_draft(draft_id: str, change_request: str) -> Any:
    concrete_path = f"/api/drafts/{draft_id}/revise"
    body = revision_body(change_request)
    return api_request("POST", concrete_path, json_body=body)


def approve_draft(draft_id: str, frequency: str,
                  approved_template: Optional[str]) -> Any:
    concrete_path = f"/api/drafts/{draft_id}/approve"
    body = approval_body(frequency, approved_template)
    return api_request("POST", concrete_path, json_body=body)


# ============================================================
# 6. Backend 응답 정규화
# ============================================================
def first_value(data: Dict[str, Any], keys: List[str], default: Any = "") -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def extract_draft_id(data: Any) -> Optional[str]:
    """POST 응답에서 draft_id/id/thread_id를 재귀적으로 찾음."""
    if isinstance(data, dict):
        for key in ("draft_id", "id", "newsletter_id", "thread_id"):
            value = data.get(key)
            if value not in (None, ""):
                return str(value)

        for key in ("draft", "data", "result", "newsletter"):
            if key in data:
                found = extract_draft_id(data[key])
                if found:
                    return found

    return None


def normalize_draft(item: Dict[str, Any]) -> Dict[str, Any]:
    draft_id = first_value(
        item,
        ["draft_id", "id", "newsletter_id", "thread_id"],
        "",
    )

    title = first_value(
        item,
        ["title", "headline", "subject", "name"],
        f"뉴스레터 {draft_id}" if draft_id else "뉴스레터",
    )

    summary = first_value(
        item,
        ["summary", "head", "headline_summary", "description", "preview", "request_text"],
        "",
    )

    status = first_value(
        item,
        ["status", "state", "approval_status"],
        "",
    )

    score = first_value(
        item,
        ["score", "quality_score", "review_score"],
        "",
    )

    frequency = first_value(
        item,
        ["frequency", "period", "cycle", "schedule"],
        "",
    )

    date = first_value(
        item,
        ["date", "created_at", "updated_at", "generated_at"],
        "",
    )

    return {
        "id": str(draft_id),
        "title": str(title),
        "summary": str(summary),
        "status": str(status),
        "score": score,
        "frequency": str(frequency),
        "date": str(date),
        "raw": item,
    }


def extract_draft_list(payload: Any) -> List[Dict[str, Any]]:
    """
    GET /api/drafts 응답이
    - [...]
    - {"drafts": [...]}
    - {"items": [...]}
    - {"data": [...]}
    등 어느 형태여도 최대한 정규화.
    """
    raw_items: List[Any] = []

    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        for key in ("drafts", "items", "results", "data", "newsletters"):
            value = payload.get(key)
            if isinstance(value, list):
                raw_items = value
                break

        if not raw_items and any(
            key in payload for key in ("draft_id", "id", "newsletter_id", "thread_id")
        ):
            raw_items = [payload]

    return [
        normalize_draft(item)
        for item in raw_items
        if isinstance(item, dict)
    ]


def safe_text(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def frequency_label(value: str) -> str:
    return {
        "every_30_minutes": "30분마다",
        "hourly": "매시간",
        "daily": "매일",
        "weekly": "매주",
    }.get(value, value)


def status_label(value: str) -> str:
    return {
        "pending": "승인 대기",
        "approved": "승인 완료",
        "sent": "발송 완료",
        "revision": "수정 중",
        "revising": "수정 중",
    }.get(value, value or "-")


def show_api_error(exc: BackendAPIError):
    st.error(
        f"백엔드 API 오류"
        + (f" · HTTP {exc.status_code}" if exc.status_code else "")
    )
    if exc.detail:
        with st.expander("서버 응답 상세"):
            st.code(str(exc.detail), language="text")


# ============================================================
# 7. Session State
# ============================================================
if "frequency" not in st.session_state:
    st.session_state.frequency = "daily"

if "active_draft_id" not in st.session_state:
    st.session_state.active_draft_id = None

if "last_api_message" not in st.session_state:
    st.session_state.last_api_message = ""

if "target_draft_select" not in st.session_state:
    st.session_state.target_draft_select = ""


def sync_active_draft():
    """사용자가 드롭다운에서 고른 초안만 현재 미리보기로 연다."""
    st.session_state.active_draft_id = (
        st.session_state.target_draft_select or None
    )


# ============================================================
# 8. Header / Backend 상태
# ============================================================
st.markdown("## 📰 Newsletter Frontend")
st.markdown(
    '<div class="flow">'
    'Streamlit Frontend → Remote Newsletter Agent API → Backend Workflow'
    '</div>',
    unsafe_allow_html=True,
)

status_col, docs_col = st.columns([4, 1])

with status_col:
    try:
        status_data = backend_status()
        st.markdown(
            f'<div class="backend-line">🟢 Backend 연결됨 · '
            f'{safe_text(BACKEND_BASE_URL)}</div>',
            unsafe_allow_html=True,
        )
    except BackendAPIError:
        st.markdown(
            f'<div class="backend-line">🔴 Backend 연결 확인 필요 · '
            f'{safe_text(BACKEND_BASE_URL)}</div>',
            unsafe_allow_html=True,
        )

with docs_col:
    st.link_button(
        "API 문서",
        DOCS_URL,
        use_container_width=True,
    )


# ============================================================
# 9. Backend 초안 목록 조회
# ============================================================
try:
    draft_payload = list_drafts_raw()
    drafts = extract_draft_list(draft_payload)
except BackendAPIError as exc:
    drafts = []
    show_api_error(exc)

draft_ids = [d["id"] for d in drafts if d["id"]]

if st.session_state.pop("clear_active_draft", False):
    st.session_state.active_draft_id = None
    st.session_state.target_draft_select = ""

pending_id = st.session_state.pop("pending_active_draft_id", None)
if pending_id in draft_ids:
    st.session_state.active_draft_id = pending_id
    st.session_state.target_draft_select = pending_id

if st.session_state.active_draft_id not in draft_ids:
    st.session_state.active_draft_id = None
if st.session_state.target_draft_select not in draft_ids:
    st.session_state.target_draft_select = ""


# ============================================================
# 10. 상단 Compact 입력영역
# ============================================================
input1_col, input2_col = st.columns([1, 1], gap="medium")

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
        if st.button(
            "🚀 뉴스레터 요청", type="primary", use_container_width=True
        ):
            if not newsletter_request.strip():
                st.warning("뉴스레터 요청 내용을 입력해 주세요.")
            else:
                try:
                    with st.spinner("백엔드에 뉴스레터 생성을 요청하고 있습니다..."):
                        result = request_newsletter(newsletter_request.strip())
                    new_id = extract_draft_id(result)
                    if new_id:
                        st.session_state.pending_active_draft_id = new_id
                    st.session_state.last_api_message = (
                        "뉴스레터 요청이 백엔드에 전달되었습니다."
                    )
                    st.rerun()
                except BackendAPIError as exc:
                    show_api_error(exc)

with input2_col:
    with st.container(border=True):
        st.markdown(
            '<div class="section-label">② 수정 요청 / 최종 승인</div>',
            unsafe_allow_html=True,
        )

        if drafts:
            title_map = {d["id"]: d["title"] for d in drafts}
            target_id = st.selectbox(
                "수정/승인 대상 뉴스",
                [""] + draft_ids,
                format_func=lambda draft_id: (
                    "— 뉴스레터를 선택해 주세요 —"
                    if not draft_id else title_map.get(draft_id, draft_id)
                ),
                key="target_draft_select",
                on_change=sync_active_draft,
            )
            selected_draft = next(
                (d for d in drafts if d["id"] == target_id), None
            )
            is_approved = bool(
                selected_draft
                and selected_draft["status"] in ("approved", "sent")
            )
            controls_disabled = selected_draft is None or is_approved

            if is_approved:
                st.info("이미 승인된 뉴스레터입니다. 수정하거나 다시 승인할 수 없습니다.")

            change_request = st.text_area(
                "이렇게 바꾸어주세요",
                placeholder=(
                    "예: 너무 기술적인 표현은 줄이고, 핵심 뉴스 5개를 먼저 보여준 뒤 "
                    "각 항목을 이해하기 쉽게 설명해 주세요."
                ),
                key="change_request_combined",
                disabled=controls_disabled,
            )

            action1, action2, action3 = st.columns([1.0, 1.1, .9])
            with action1:
                revise_clicked = st.button(
                    "↻ 수정 요청",
                    use_container_width=True,
                    disabled=controls_disabled,
                )
            with action2:
                approve_clicked = st.button(
                    "✅ 최종 승인",
                    type="primary",
                    use_container_width=True,
                    disabled=controls_disabled,
                )
            with action3:
                selected_frequency = st.selectbox(
                    "주기",
                    FREQUENCY_OPTIONS,
                    index=FREQUENCY_OPTIONS.index(st.session_state.frequency),
                    format_func=frequency_label,
                    key="frequency_select",
                    disabled=controls_disabled,
                )
                st.session_state.frequency = selected_frequency

            if revise_clicked:
                if not change_request.strip():
                    st.warning("'이렇게 바꾸어주세요'에 수정 내용을 입력해 주세요.")
                else:
                    try:
                        with st.spinner("백엔드에 수정 요청을 전달하고 있습니다..."):
                            revise_draft(target_id, change_request.strip())
                        st.session_state.last_api_message = (
                            "수정 요청이 백엔드에 전달되었습니다."
                        )
                        st.rerun()
                    except BackendAPIError as exc:
                        show_api_error(exc)

            if approve_clicked:
                try:
                    active_detail = get_draft_raw(target_id)
                    approved_template = first_value(
                        active_detail if isinstance(active_detail, dict) else {},
                        ["approved_template", "article_html"],
                        None,
                    )
                    with st.spinner("최종 승인과 주기 설정을 백엔드에 전달하고 있습니다..."):
                        approve_draft(
                            target_id,
                            st.session_state.frequency,
                            approved_template,
                        )
                    st.session_state.last_api_message = (
                        "최종 승인되었습니다. 주기: "
                        f"{frequency_label(st.session_state.frequency)}"
                    )
                    st.session_state.clear_active_draft = True
                    st.rerun()
                except BackendAPIError as exc:
                    show_api_error(exc)
        else:
            st.info(
                "백엔드에 조회 가능한 초안이 없습니다. "
                "먼저 왼쪽에서 뉴스레터를 요청해 주세요."
            )
            _, _, period_col = st.columns([1.0, 1.1, .9])
            with period_col:
                selected_frequency = st.selectbox(
                    "주기",
                    FREQUENCY_OPTIONS,
                    index=FREQUENCY_OPTIONS.index(st.session_state.frequency),
                    format_func=frequency_label,
                    key="frequency_select_empty",
                )
                st.session_state.frequency = selected_frequency

if st.session_state.last_api_message:
    st.success(st.session_state.last_api_message)
    st.session_state.last_api_message = ""


# ============================================================
# 11. 선택한 뉴스레터 템플릿 표시
# ============================================================
if drafts and st.session_state.active_draft_id:
    st.markdown("---")
    try:
        active_detail = get_draft_raw(st.session_state.active_draft_id)
    except BackendAPIError as exc:
        active_detail = {}
        show_api_error(exc)

    if isinstance(active_detail, dict) and active_detail:
        title = safe_text(first_value(active_detail, ["title", "subject"], "뉴스레터"))

        st.markdown("### ③ 뉴스레터 미리보기")
        st.caption("백엔드가 생성한 HTML 템플릿을 수정하지 않고 표시합니다.")
        st.markdown(f"#### {title}")

        article_html = first_value(
            active_detail,
            ["article_html", "approved_template"],
            "",
        )
        if article_html:
            st.markdown(
                f'<div class="newsletter-preview">{article_html}</div>',
                unsafe_allow_html=True,
            )
        else:
            markdown_text = active_detail.get("markdown") or ""
            if markdown_text:
                st.markdown(markdown_text)
            else:
                st.info("표시할 뉴스레터 내용이 없습니다.")
