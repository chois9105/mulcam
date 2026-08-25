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
_EMAIL_TMPL = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, "Malgun Gothic", sans-serif;
          line-height: 1.7; color: #222; background: #f5f5f7; margin: 0; padding: 24px; }}
  .container {{ max-width: 640px; margin: 0 auto; background: #fff;
                border-radius: 12px; overflow: hidden; }}
  .header {{ background: #1d6f42; color: #fff; padding: 24px; }}
  .header h1 {{ margin: 0; font-size: 20px; }}
  .content {{ padding: 24px; }}
  .content h1, .content h2 {{ font-size: 17px; margin: 22px 0 8px; }}
  .content a {{ color: #1d6f42; }}
  .sources {{ margin-top: 24px; padding-top: 16px; border-top: 1px solid #e5e5e5;
              font-size: 13px; }}
  .sources li {{ margin-bottom: 6px; }}
  .footer {{ background: #fafafa; padding: 16px 24px; font-size: 12px; color: #666; }}
</style>
</head>
<body>
  <div class="container">
    <div class="header"><h1>{title}</h1></div>
    <div class="content">{content}{sources}</div>
    <div class="footer">{footer}</div>
  </div>
</body>
</html>"""


def to_email_html(
    title: str,
    markdown_text: str,
    sources: Optional[List[dict]] = None,
    footer: str = "본 뉴스레터는 수집된 기사를 근거로 자동 생성되었습니다.",
) -> str:
    """이메일로 보낼 전체 HTML 문서를 만든다."""
    src_html = ""
    if sources:
        items = "\n".join(
            f'<li><a href="{s.get("link", "")}">[{s.get("n", i)}] {s.get("title", "")}</a>'
            f' ({s.get("source", "")})</li>'
            for i, s in enumerate(sources, 1)
        )
        src_html = f'<div class="sources"><strong>근거 기사</strong><ul>{items}</ul></div>'

    return _EMAIL_TMPL.format(
        title=title,
        content=md_to_html(markdown_text),
        sources=src_html,
        footer=footer,
    )
