"""뉴스레터 에이전트 메인 애플리케이션"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional
from project_newsletter import NewsletterAgent
from email_utils import EmailService, EmailTemplate
from rss_collector import RSSCollector
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
    description="RSS 수집 + RAG 기반 뉴스레터 자동 생성 및 배송 API",
    version="1.1.0"
)

# ---------------------------------------------------------------
# CORS 설정
#
# 프론트엔드(:8000)와 백엔드(:8001)가 서로 다른 포트에서 돈다.
# 브라우저는 보안상 다른 주소로의 요청을 기본으로 막기 때문에
# "이 주소들은 허용한다"고 미리 알려줘야 한다.
# ---------------------------------------------------------------
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000,"      # 프론트엔드 FastAPI
        "http://localhost:8501,http://127.0.0.1:8501",      # Streamlit
    ).split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# RAG 라우터 등록 (/rag/build, /rag/ask, /rag/summarize ...)
from rag_api import router as rag_router
app.include_router(rag_router)


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
        "service": "newsletter-backend",
        "port": int(os.getenv("PORT", 8001)),
        "cors_allowed": ALLOWED_ORIGINS,
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


@app.get("/news/rss")
async def fetch_rss_news():
    """RSS 피드에서 최신 뉴스 수집"""
    try:
        logger.info("RSS 뉴스 수집 시작")
        collector = RSSCollector()
        news = collector.fetch_all_news()

        logger.info(f"수집된 뉴스: {len(news)}개")
        return {
            "success": True,
            "count": len(news),
            "news": news,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"RSS 수집 오류: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"RSS 수집 중 오류: {str(e)}"
        )


@app.post("/newsletter/from-rss")
async def generate_newsletter_from_rss(request: NewsletterRequest):
    """RSS 뉴스를 기반으로 뉴스레터 생성"""
    try:
        logger.info("RSS 기반 뉴스레터 생성 시작")

        # RSS 뉴스 수집
        collector = RSSCollector()
        rss_news = collector.fetch_all_news()

        # 뉴스 요약
        news_text = "\n".join([
            f"제목: {n['title']}\n요약: {n['description']}"
            for n in rss_news[:10]
        ])

        agent = NewsletterAgent()
        newsletter = agent.run(f"{request.topic}\n\n최신 뉴스:\n{news_text}")

        # 이메일 발송
        email_results = None
        if request.send_email and request.recipients:
            email_service = EmailService()
            valid_recipients = [
                r for r in request.recipients
                if email_service.validate_email(r)
            ]

            if valid_recipients:
                html_content = EmailTemplate.create_newsletter_html(
                    title=request.topic,
                    content=newsletter
                )
                email_results = email_service.send_newsletter(
                    recipients=valid_recipients,
                    subject=f"뉴스레터: {request.topic}",
                    newsletter_html=html_content
                )
                logger.info(f"이메일 발송 완료")

        return NewsletterResponse(
            success=True,
            topic=request.topic,
            newsletter=newsletter,
            email_results=email_results,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"RSS 기반 뉴스레터 생성 오류: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"오류: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        # 프론트엔드가 8000 을 쓰므로 백엔드는 8001 을 기본으로 한다
        port=int(os.getenv("PORT", 8001)),
    )
