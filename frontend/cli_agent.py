"""
cli_agent.py
터미널에서 직접 실행할 수 있는 대화형 Python CLI 멀티 에이전트 뉴스레터 시스템
"""

import sys
from agent_graph import workflow_engine


def print_banner():
    print("=" * 65)
    print(" 🍎 AgentLetter CLI — 맞춤형 AI 뉴스레터 제작 & 자동 검수 시스템")
    print("=" * 65)


def run_cli():
    print_banner()
    
    keywords_input = input("📌 관심 키워드를 쉼표(,)로 구분하여 입력하세요 (기본: LangGraph, FastAPI, AWS): ").strip()
    if keywords_input:
        keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]
    else:
        keywords = ["LangGraph", "FastAPI", "AWS EventBridge"]

    print("\n⏳ 발송 주기를 선택하세요:")
    print(" 1) 매일 (Daily)")
    print(" 2) 주간 (Weekly)")
    print(" 3) 월간 (Monthly)")
    freq_choice = input("선택 (1/2/3, 기본: 1): ").strip()
    freq_map = {"1": "daily", "2": "weekly", "3": "monthly"}
    frequency = freq_map.get(freq_choice, "daily")

    print("\n" + "-" * 65)
    print(f"🚀 [LangGraph 멀티 에이전트 파이프라인 가동 시작]")
    print(f"   - 관심 키워드: {', '.join(keywords)}")
    print(f"   - 발송 주기: {frequency.upper()}")
    print("-" * 65)

    draft_id = "cli-draft-001"
    
    # 1. 파이프라인 실행
    print(" [1/4] 🔍 리서치 에이전트: 최신 웹 문서 및 아키텍처 자료 수집 중...")
    print(" [2/4] ✍️ 작성 에이전트: 뉴스레터 초안 작성 중...")
    print(" [3/4] 🤖 검수 에이전트: 가독성 및 사실 정확도 LLM-as-a-Judge 평가 중...")
    
    draft = workflow_engine.run_pipeline(draft_id, keywords, frequency)

    print("\n" + "=" * 65)
    print(f" 📄 [생성된 뉴스레터 헤드라인]")
    print(f"  • 제목: {draft['title']}")
    print(f"  • 요약: {draft['summary']}")
    print(f"  • 검수 점수: {draft['score']}점 ({draft['score_grade']})")
    print(f"  • 가독성: {draft['audit_report']['readability']}점 / 사실정확도: {draft['audit_report']['fact_accuracy']}점")
    print(f"  • 검수 의견: {draft['audit_report']['reviewer_comment']}")
    print("=" * 65)

    print("\n⏸️ [Human-in-the-loop State Checkpoint]")
    print("   FastAPI interrupt_before 상태에 도달하여 사용자 승인을 기다립니다.\n")

    while True:
        print("어떻게 진행하시겠습니까?")
        print(" 1) [최종 승인 및 발송 확정] (AWS EventBridge/SES 큐 전송)")
        print(" 2) [수정 요청] (작성 에이전트로 피드백 전달 후 재작성)")
        print(" 3) [전문 본문 전체 보기]")
        print(" 4) [종료]")
        
        choice = input("\n선택 (1/2/3/4): ").strip()

        if choice == "1":
            approved = workflow_engine.resume_approval(draft_id)
            print("\n🎉 [성공] 뉴스레터가 최종 승인되었습니다!")
            print(f"   - 발송 상태: {approved['status'].upper()}")
            print(f"   - AWS EventBridge 발송 큐 등록 완료.")
            break
        elif choice == "2":
            feedback = input("\n📝 에이전트에게 전달할 수정 피드백을 입력하세요: ").strip()
            if not feedback:
                feedback = "기술적 깊이를 더 보강하고 실무 체크포인트를 추가해주세요."
            print(f"\n↻ [LangGraph Conditional Loop] 작성 에이전트로 피드백 전송 및 재작성 중...")
            revised = workflow_engine.resume_revision(draft_id, feedback)
            print("\n✨ [재작성 완료]")
            print(f"  • 새 점수: {revised['score']}점 ({revised['score_grade']})")
            print(f"  • 검수 의견: {revised['audit_report']['reviewer_comment']}\n")
        elif choice == "3":
            print("\n" + "=" * 65)
            print(draft["article_html"].replace("<div", "\n<div"))
            print("=" * 65 + "\n")
        elif choice == "4":
            print("\n종료합니다.")
            break
        else:
            print("올바른 번호를 선택해주세요.")


if __name__ == "__main__":
    run_cli()
