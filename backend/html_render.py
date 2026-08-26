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
INK = "#1F2328"            # 제목
SOFT = "#5B6470"           # 본문
FAINT = "#9AA1AB"          # 잔글씨
LINE = "#E5E7EB"           # 얇은 테두리
BG = "#FFFFFF"

_FONT = "-apple-system, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif"


def _split_items(markdown_text: str):
    """
    '**제목** [n]' + 설명 형태를 카드 단위로 쪼갠다.
    형식이 다르면 통째로 하나로 돌려준다.
    """
    headline, items, cur = "", [], None

    for ln in markdown_text.splitlines():
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
    meta: str = "",
) -> str:
    """
    이메일 HTML.

    화면(AgentLetter Compact)의 생김새를 그대로 옮겼다.
      - 흰 바탕에 얇은 회색 테두리 카드
      - 제목은 굵은 검정, 본문은 회색, 근거 번호만 빨강
      - 카드 아래 회색 잔글씨 메타 줄

    메일 프로그램은 <style> 을 지우는 경우가 많아 스타일을 각 요소에 직접 넣는다.
    """
    headline, items = _split_items(markdown_text)

    if items:
        cards = ""
        for it in items:
            ref = (f'<span style="color:{BRAND};font-weight:600;font-size:13px;">'
                   f'&nbsp;{it["ref"]}</span>' if it["ref"] else "")
            cards += (
                f'<tr><td style="padding:0 0 12px;">'
                f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
                f'style="border:1px solid {LINE};border-radius:9px;">'
                f'<tr><td style="padding:16px 18px;">'
                f'<div style="font-size:15.5px;font-weight:700;color:{INK};'
                f'line-height:1.5;margin-bottom:6px;">{it["title"]}{ref}</div>'
                f'<div style="font-size:14px;color:{SOFT};line-height:1.7;">'
                f'{" ".join(it["body"])}</div>'
                f'</td></tr></table></td></tr>'
            )
        body_html = (f'<table width="100%" cellpadding="0" cellspacing="0" '
                     f'border="0">{cards}</table>')
    else:
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
                f'<span style="color:{FAINT};">{sc.get("source", "")}</span></div>'
            )
        src_html = (
            f'<div style="margin-top:24px;padding-top:18px;border-top:1px solid {LINE};">'
            f'<div style="font-size:13.5px;font-weight:700;color:{INK};margin-bottom:6px;">'
            f'근거 기사</div>'
            f'<div style="font-size:12.5px;color:{FAINT};margin-bottom:12px;">'
            f'제목을 누르면 원문으로 이동합니다.</div>{rows}</div>'
        )

    meta_html = (f'<div style="font-size:12.5px;color:{FAINT};margin-top:2px;'
                 f'margin-bottom:20px;">{meta}</div>') if meta else ""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head>
<body style="margin:0;padding:28px 16px 44px;background:{BG};font-family:{_FONT};">
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td align="center">
  <table width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;">

    <tr><td style="padding-bottom:22px;">
      <div style="font-size:26px;font-weight:700;color:{INK};letter-spacing:-.5px;">
        &#128240;&nbsp; AgentLetter
      </div>
      <div style="font-size:12.5px;color:{FAINT};margin-top:4px;">
        Research &rarr; Writer &rarr; Reviewer &rarr; Human Approval &rarr; Send
      </div>
    </td></tr>

    <tr><td>
      <div style="font-size:19px;font-weight:700;color:{INK};line-height:1.45;">
        {headline or title}</div>
      {meta_html}
      {body_html}
      {src_html}
    </td></tr>

    <tr><td style="padding-top:22px;font-size:12.5px;color:{FAINT};line-height:1.6;">
      {footer}
    </td></tr>

  </table>
</td></tr>
</table>
</body>
</html>"""
