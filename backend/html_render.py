"""
마크다운 -> HTML 변환

RAG 엔진은 뉴스레터를 마크다운으로 만든다.
그런데 쓰는 곳마다 필요한 형태가 다르다.

  1) 프론트엔드 대시보드  : HTML '조각' (프론트 CSS 클래스에 맞춤)
  2) 이메일               : <html>...</html> 전체 문서

두 가지를 여기서 만든다.
"""

from __future__ import annotations

import re
from typing import List, Optional

import markdown as md

# 표·줄바꿈·목차 정도만 켠다 (과한 확장은 안 씀)
_EXTENSIONS = ["extra", "nl2br", "sane_lists"]


def md_to_html(text: str) -> str:
    """마크다운을 HTML 조각으로 바꾼다. <html>, <body> 는 붙이지 않는다."""
    if not text:
        return ""
    return md.markdown(text, extensions=_EXTENSIONS)


# ---------------------------------------------------------------
# 1) 대시보드용
# ---------------------------------------------------------------
# 프론트엔드(frontend/agent_graph.py)가 쓰는 CSS 클래스에 맞춘다.
#   .article-hero-box / .article-hero-title / .article-hero-text
#   .article-key-takeaways / .takeaways-title / .takeaway-list

_HERO_TMPL = """<div class="article-hero-box">
  <div class="article-hero-title">💡 이번 호 핵심 요약</div>
  <div class="article-hero-text">{summary}</div>
</div>
"""

_TAKEAWAY_TMPL = """<div class="article-key-takeaways">
  <div class="takeaways-title">🔗 근거 기사</div>
  <ul class="takeaway-list">
{items}
  </ul>
</div>
"""


def _extract_summary(markdown_text: str) -> str:
    """'오늘의 한 줄' 같은 마무리 문장을 찾아 핵심 요약으로 쓴다."""
    for pattern in (r"오늘의 한 줄\s*[:：]?\s*(.+)", r"한 줄 정리\s*[:：]?\s*(.+)"):
        m = re.search(pattern, markdown_text)
        if m:
            return m.group(1).strip().lstrip("*").strip()
    # 없으면 첫 번째 일반 문단
    for line in markdown_text.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "-", "*", ">", "|")):
            return line[:200]
    return "수집된 기사를 근거로 작성된 뉴스레터입니다."


def to_dashboard_html(
    markdown_text: str,
    sources: Optional[List[dict]] = None,
    summary: Optional[str] = None,
) -> str:
    """
    대시보드에 그대로 넣을 HTML 조각을 만든다.

    구성: 핵심 요약 박스 + 본문 + 근거 기사 링크 목록
    """
    hero = _HERO_TMPL.format(summary=summary or _extract_summary(markdown_text))
    body = md_to_html(markdown_text)

    takeaways = ""
    if sources:
        items = "\n".join(
            f'    <li><a href="{s.get("link", "")}" target="_blank" rel="noopener">'
            f'[{s.get("n", i)}] {s.get("title", "")}</a> '
            f'<span class="source-name">({s.get("source", "")})</span></li>'
            for i, s in enumerate(sources, 1)
        )
        takeaways = _TAKEAWAY_TMPL.format(items=items)

    return hero + body + takeaways


# ---------------------------------------------------------------
# 2) 이메일용
# ---------------------------------------------------------------
# ---------------------------------------------------------------
# 이메일 템플릿
#
# 화면(AgentLetter Compact)과 같은 느낌으로 맞췄다.
#   - 빨간 포인트 색 (#E8453C)
#   - 기사마다 카드 형태
#
# 메일 프로그램은 <style> 을 지우는 경우가 많아서
# 스타일을 각 요소에 직접(inline) 넣는다. 지메일에서도 그대로 보인다.
# ---------------------------------------------------------------

BRAND = "#E8453C"          # 화면 버튼과 같은 빨강
INK = "#1F2328"
SOFT = "#5B6470"
LINE = "#E5E7EB"
BG = "#F5F5F7"

_FONT = "-apple-system, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif"


def _card(title_html: str, body_html: str) -> str:
    """기사 한 건을 카드로 감싼다."""
    return (
        f'<tr><td style="padding:0 0 14px;">'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border:1px solid {LINE};border-radius:10px;border-left:4px solid {BRAND};">'
        f'<tr><td style="padding:16px 18px;">'
        f'<div style="font-size:15.5px;font-weight:700;color:{INK};line-height:1.5;'
        f'margin-bottom:6px;">{title_html}</div>'
        f'<div style="font-size:14px;color:{SOFT};line-height:1.7;">{body_html}</div>'
        f'</td></tr></table></td></tr>'
    )


def _split_items(markdown_text: str):
    """
    '**제목** [n]' + 설명 형태를 카드 단위로 쪼갠다.
    형식이 다르면 통째로 하나로 돌려준다.
    """
    lines = markdown_text.splitlines()
    headline, items, cur = "", [], None

    for ln in lines:
        t = ln.strip()
        if not t:
            continue
        if t.startswith("#"):
            if not headline:
                headline = t.lstrip("#").strip()
            continue
        m = re.match(r"^\*\*(.+?)\*\*\s*(\[\d+\])?\s*$", t)
        if m:
            if cur:
                items.append(cur)
            cur = {"title": m.group(1), "ref": m.group(2) or "", "body": []}
        elif cur:
            cur["body"].append(t)
    if cur:
        items.append(cur)
    return headline, items


def to_email_html(
    title: str,
    markdown_text: str,
    sources: Optional[List[dict]] = None,
    footer: str = "수집된 기사를 근거로 자동 생성된 뉴스레터입니다.",
) -> str:
    """이메일로 보낼 전체 HTML 문서를 만든다."""
    headline, items = _split_items(markdown_text)

    if items:
        cards = ""
        for it in items:
            ref = (f'<span style="color:{BRAND};font-weight:600;">&nbsp;{it["ref"]}</span>'
                   if it["ref"] else "")
            cards += _card(it["title"] + ref, " ".join(it["body"]))
        body_html = f'<table width="100%" cellpadding="0" cellspacing="0" border="0">{cards}</table>'
    else:
        # 형식이 예상과 다르면 통째로 변환해서 넣는다
        body_html = (f'<div style="font-size:14.5px;color:{INK};line-height:1.8;">'
                     f'{md_to_html(markdown_text)}</div>')

    src_html = ""
    if sources:
        rows = ""
        for i, sc in enumerate(sources, 1):
            rows += (
                f'<div style="margin-bottom:8px;font-size:13px;line-height:1.6;">'
                f'<span style="color:{BRAND};font-weight:600;">[{sc.get("n", i)}]</span> '
                f'<a href="{sc.get("link", "")}" style="color:{INK};text-decoration:none;">'
                f'{sc.get("title", "")}</a> '
                f'<span style="color:#9AA1AB;">{sc.get("source", "")}</span></div>'
            )
        src_html = (
            f'<div style="margin-top:26px;padding-top:18px;border-top:1px solid {LINE};">'
            f'<div style="font-size:13px;font-weight:700;color:{INK};margin-bottom:12px;">'
            f'근거 기사 &middot; 제목을 누르면 원문으로 이동합니다</div>{rows}</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head>
<body style="margin:0;padding:24px 12px;background:{BG};font-family:{_FONT};">
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td align="center">
  <table width="620" cellpadding="0" cellspacing="0" border="0"
         style="max-width:620px;background:#ffffff;border-radius:14px;overflow:hidden;">

    <tr><td style="padding:22px 26px;border-bottom:3px solid {BRAND};">
      <div style="font-size:19px;font-weight:700;color:{INK};letter-spacing:-0.2px;">
        &#128240;&nbsp; AgentLetter
      </div>
      <div style="font-size:12px;color:#9AA1AB;margin-top:3px;">
        Research &rarr; Writer &rarr; Reviewer &rarr; Human Approval &rarr; Send
      </div>
    </td></tr>

    <tr><td style="padding:26px 26px 8px;">
      <div style="font-size:21px;font-weight:700;color:{INK};line-height:1.4;
                  margin-bottom:20px;">{headline or title}</div>
      {body_html}
      {src_html}
    </td></tr>

    <tr><td style="padding:18px 26px;background:#FAFAFB;border-top:1px solid {LINE};
                   font-size:12px;color:#9AA1AB;line-height:1.6;">
      {footer}
    </td></tr>

  </table>
</td></tr>
</table>
</body>
</html>"""
