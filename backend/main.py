"""뉴스레터 에이전트 메인 애플리케이션"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional
from newsletter_agent import NewsletterAgent
from email_utils import EmailService, EmailTemplate
import logging
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Newsletter Agent API",
    description="AI 기반 뉴스레터 자동 생성 및 배송 API",
    version="1.0.0"
)


# 요청 모델
class NewsletterRequest(BaseModel):
    """뉴스레터 생성 요청"""
    topic: str = Field(..., description="뉴스레터 주제")
    recipients: Optional[List[str]] = Field(
        default=None,
        description="이메일 수신자 리스트"
    )
    send_email: bool = Field(
        default=False,
        description="이메일 발송 여부"
    )


class NewsletterResponse(BaseModel):
    """뉴스레터 생성 응답"""
    success: bool
    topic: str
    newsletter: str
    email_results: Optional[dict] = None
    timestamp: str


# API 엔드포인트
@app.get("/health")
async def health_check():
    """헬스 체크"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.post("/generate", response_model=NewsletterResponse)
async def generate_newsletter(request: NewsletterRequest):
    """뉴스레터 생성"""
    try:
        logger.info(f"뉴스레터 생성 시작: {request.topic}")

        # 뉴스레터 생성
        agent = NewsletterAgent()
        newsletter = agent.run(request.topic)

        # 이메일 발송 (선택사항)
        email_results = None
        if request.send_email and request.recipients:
            logger.info(f"{len(request.recipients)}명에게 이메일 발송 시작")
            email_service = EmailService()

            # 이메일 유효성 검증
            valid_recipients = [
                r for r in request.recipients
                if email_service.validate_email(r)
            ]

            if valid_recipients:
                # HTML 템플릿 생성
                html_content = EmailTemplate.create_newsletter_html(
                    title=request.topic,
                    content=newsletter
                )

                # 이메일 발송
                email_results = email_service.send_newsletter(
                    recipients=valid_recipients,
                    subject=f"뉴스레터: {request.topic}",
                    newsletter_html=html_content
                )
                logger.info(f"이메일 발송 완료 - 성공: {email_results['success']}, 실패: {email_results['failed']}")

        return NewsletterResponse(
            success=True,
            topic=request.topic,
            newsletter=newsletter,
            email_results=email_results,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"뉴스레터 생성 오류: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"뉴스레터 생성 중 오류 발생: {str(e)}"
        )


@app.post("/validate-emails")
async def validate_emails(emails: List[str]):
    """이메일 주소 검증"""
    email_service = EmailService()
    results = {
        "valid": [],
        "invalid": []
    }

    for email in emails:
        if email_service.validate_email(email):
            results["valid"].append(email)
        else:
            results["invalid"].append(email)

    return results


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000))
    )
