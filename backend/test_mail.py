"""
메일 설정 점검

비밀번호를 화면에 찍지 않는다. 무엇이 비었는지, 형식이 맞는지만 알려준다.

실행
    python test_mail.py           설정 점검 + 로그인만 시도
    python test_mail.py --send    실제로 한 통 보낸다 (MAIL_DRY_RUN=false 여야 함)
"""

import sys

from mailer import diagnose, is_dry_run, send_draft, test_login


def line(t):
    print("\n" + "=" * 60)
    print(t)
    print("=" * 60)


def main() -> int:
    line("1. 설정 점검")
    d = diagnose()
    print(f"  SMTP        : {d['smtp_server']}:{d['smtp_port']}")
    print(f"  보내는 사람 : {d['sender']}")
    print(f"  받는 사람   : {d['to']}")
    print(f"  비밀번호    : {'설정됨 (' + str(d['password_length']) + '자리)' if d['password_set'] else '비어 있음'}")
    print(f"  DRY_RUN     : {d['dry_run']}  {'(실제로 보내지 않음)' if d['dry_run'] else '(실제로 보냄)'}")

    if d["problems"]:
        print("\n  고쳐야 할 것:")
        for p in d["problems"]:
            print(f"    - {p}")
        print("\n  backend/.env 를 열어 채워주세요.")
        print("  지메일 앱 비밀번호 발급: https://myaccount.google.com/apppasswords")
        return 1
    print("\n  설정 이상 없음")

    line("2. 로그인 시도 (메일은 보내지 않음)")
    r = test_login()
    if r["ok"]:
        print(f"  {r['message']}")
    else:
        print(f"  실패: {r['reason']}")
        if r.get("hint"):
            print(f"  힌트: {r['hint']}")
        for p in r.get("problems", []):
            print(f"    - {p}")
        return 1

    if "--send" not in sys.argv:
        line("완료")
        print("실제로 한 통 보내보려면:  python test_mail.py --send")
        if is_dry_run():
            print("(먼저 .env 의 MAIL_DRY_RUN 을 false 로 바꿔야 실제 발송됩니다)")
        return 0

    line("3. 실제 발송")
    sample = {
        "title": "발송 테스트",
        "markdown": "# 발송 테스트\n\n**뉴스레터 발송이 정상 동작합니다** [1]\n"
                    "이 메일이 보이면 SMTP 설정이 올바른 것입니다.\n",
        "sources": [{"title": "테스트 기사", "summary": "테스트", "url": "https://example.com"}],
    }
    res = send_draft(sample)
    if res.get("sent"):
        print(f"  발송 완료 -> {res['to']}")
        print(f"  제목: {res['subject']}")
        print("\n  메일함을 확인해 주세요.")
    elif res.get("dry_run"):
        print(f"  {res['message']}")
        print(f"  보낼 대상: {res['would_send']['to']}")
        print("  실제로 보내려면 .env 의 MAIL_DRY_RUN 을 false 로 바꾸세요.")
    else:
        print(f"  실패: {res.get('reason')}")
        if res.get("hint"):
            print(f"  힌트: {res['hint']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
