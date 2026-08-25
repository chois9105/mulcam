"""
메일 발송

이번 프로젝트는 한 사람에게만 보낸다. 구독자 관리 DB 를 만들지 않고
.env 의 MAIL_TO 한 줄로 끝낸다.

    SMTP_SERVER=smtp.gmail.com
    SMTP_PORT=587
    SENDER_EMAIL=본인@gmail.com
    SENDER_PASSWORD=앱비밀번호16자리
    MAIL_TO=받는사람@gmail.com
    MAIL_DRY_RUN=true

주의: 지메일은 계정 비밀번호로 로그인되지 않는다.
     2단계 인증을 켠 뒤 '앱 비밀번호'(16자리)를 따로 발급받아야 한다.
     https://myaccount.google.com/apppasswords
"""

from __future__ import annotations

import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from typing import Dict, List, Optional

from dotenv import load_dotenv

from html_render import to_email_html

load_dotenv()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def is_dry_run() -> bool:
    return _env("MAIL_DRY_RUN", "true").lower() != "false"


def valid_email(addr: str) -> bool:
    return bool(EMAIL_RE.match(addr.strip()))


def diagnose() -> Dict:
    """
    발송 설정을 점검한다. 비밀번호 값은 절대 출력하지 않는다.
    무엇이 비었는지, 형식이 맞는지만 알려준다.
    """
    server = _env("SMTP_SERVER", "smtp.gmail.com")
    port = _env("SMTP_PORT", "587")
    sender = _env("SENDER_EMAIL")
    password = _env("SENDER_PASSWORD")
    to = _env("MAIL_TO")

    problems: List[str] = []
    if not sender:
        problems.append("SENDER_EMAIL 이 비어 있습니다.")
    elif not valid_email(sender):
        problems.append(f"SENDER_EMAIL 형식이 이상합니다: {sender}")

    if not password:
        problems.append("SENDER_PASSWORD 가 비어 있습니다. 지메일 앱 비밀번호를 넣으세요.")
    elif " " in password:
        problems.append("SENDER_PASSWORD 에 띄어쓰기가 있습니다. 16자리를 붙여서 쓰세요.")
    elif "gmail" in server and len(password) != 16:
        problems.append(
            f"지메일 앱 비밀번호는 16자리인데 {len(password)}자리입니다. "
            "계정 비밀번호를 넣으신 건 아닌지 확인하세요."
        )

    if not to:
        problems.append("MAIL_TO 가 비어 있습니다.")
    elif not valid_email(to):
        problems.append(f"MAIL_TO 형식이 이상합니다: {to}")

    return {
        "ready": not problems,
        "problems": problems,
        "smtp_server": server,
        "smtp_port": port,
        "sender": sender or "(비어 있음)",
        "to": to or "(비어 있음)",
        "password_set": bool(password),        # 값이 아니라 여부만
        "password_length": len(password),      # 길이만
        "dry_run": is_dry_run(),
    }


def test_login() -> Dict:
    """실제로 메일을 보내지 않고 로그인만 해본다."""
    d = diagnose()
    if not d["ready"]:
        return {"ok": False, "reason": "설정이 덜 됐습니다.", "problems": d["problems"]}

    try:
        with smtplib.SMTP(d["smtp_server"], int(d["smtp_port"]), timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(d["sender"], _env("SENDER_PASSWORD"))
        return {"ok": True, "message": "로그인 성공. 발송 준비가 끝났습니다."}
    except smtplib.SMTPAuthenticationError:
        return {
            "ok": False,
            "reason": "로그인 거부",
            "hint": "앱 비밀번호가 맞는지 확인하세요. 계정 비밀번호로는 로그인되지 않습니다.",
        }
    except Exception as e:
        return {"ok": False, "reason": str(e)[:200],
                "hint": "네트워크나 SMTP 주소·포트를 확인하세요."}


def send_draft(draft: Dict, to: Optional[str] = None) -> Dict:
    """
    요약본 하나를 메일로 보낸다.

    MAIL_DRY_RUN=true 면 실제로 보내지 않고 보낼 내용만 알려준다.
    시연 중 실수로 메일이 나가는 것을 막기 위한 장치다.
    """
    d = diagnose()
    to = (to or d["to"]).strip()

    if not d["ready"]:
        return {"sent": False, "reason": "발송 설정이 덜 됐습니다.",
                "problems": d["problems"]}

    subject = f"[뉴스레터] {draft.get('title', '오늘의 뉴스')}"
    html = to_email_html(
        title=draft.get("title", "뉴스레터"),
        markdown_text=draft.get("markdown", ""),
        sources=[
            {"n": i, "title": s.get("title", ""), "source": s.get("summary", ""),
             "link": s.get("url", "")}
            for i, s in enumerate(draft.get("sources", []), 1)
        ],
    )

    if is_dry_run():
        return {
            "sent": False,
            "dry_run": True,
            "message": "MAIL_DRY_RUN=true 라 실제로 보내지 않았습니다.",
            "would_send": {"to": to, "subject": subject, "html_length": len(html)},
        }

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = d["sender"]
    msg["To"] = to
    msg.set_content("HTML 메일입니다. HTML 을 지원하는 앱에서 열어주세요.")
    msg.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(d["smtp_server"], int(d["smtp_port"]), timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(d["sender"], _env("SENDER_PASSWORD"))
            smtp.send_message(msg)
        return {"sent": True, "to": to, "subject": subject}
    except smtplib.SMTPAuthenticationError:
        return {"sent": False, "reason": "로그인 거부",
                "hint": "앱 비밀번호를 확인하세요."}
    except Exception as e:
        return {"sent": False, "reason": str(e)[:200]}
