# Newsletter Agent Backend

AI 기반 뉴스레터 자동 생성 및 배송 시스템

## 개요

LangChain과 OpenAI를 활용하여 주어진 주제에 대한 뉴스레터를 자동으로 생성하고, 메일 서버를 통해 배송하는 백엔드 애플리케이션입니다.

## 기능

- **자동 뉴스레터 생성**: AI를 통한 고품질 뉴스레터 콘텐츠 생성
- **메일 배송**: SMTP를 통한 대량 이메일 발송
- **이메일 검증**: 유효한 이메일 주소 검증
- **HTML 템플릿**: 전문적인 이메일 템플릿 제공
- **배치 처리**: 대량 이메일 발송 시 배치 처리로 안정성 확보

## 설치

### 요구사항
- Python 3.8+
- pip

### 설정

1. 저장소 클론
```bash
git clone https://github.com/yourusername/mulcam.git
cd mulcam/backend
```

2. 의존성 설치
```bash
pip install -r requirements.txt
```

3. 환경 설정
```bash
cp .env.example .env
# .env 파일에 필요한 값 입력
```

## 환경 변수

| 변수 | 설명 | 예시 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API 키 | sk-... |
| `SMTP_SERVER` | SMTP 서버 주소 | smtp.gmail.com |
| `SMTP_PORT` | SMTP 포트 | 587 |
| `SENDER_EMAIL` | 발송자 이메일 | your@gmail.com |
| `SENDER_PASSWORD` | 이메일 비밀번호 | app_password |
| `PORT` | 애플리케이션 포트 | 8000 |

## 사용

### API 서버 실행

```bash
python main.py
```

서버는 `http://localhost:8000`에서 실행됩니다.

### API 문서

`http://localhost:8000/docs`에서 Swagger UI로 API 문서 확인 가능

### 뉴스레터 생성 예시

```python
from newsletter_agent import NewsletterAgent

agent = NewsletterAgent()
newsletter = agent.run("최신 AI 트렌드")
print(newsletter)
```

### 이메일 발송 예시

```python
from email_utils import EmailService, EmailTemplate

email_service = EmailService()
html_content = EmailTemplate.create_newsletter_html(
    title="AI 뉴스레터",
    content="<p>최신 AI 소식...</p>"
)

result = email_service.send_newsletter(
    recipients=["user@example.com"],
    subject="AI 뉴스레터",
    newsletter_html=html_content
)
```

## API 엔드포인트

### POST `/generate`

뉴스레터 생성 및 배송

**요청**
```json
{
  "topic": "최신 AI 트렌드",
  "recipients": ["user@example.com"],
  "send_email": true
}
```

**응답**
```json
{
  "success": true,
  "topic": "최신 AI 트렌드",
  "newsletter": "...",
  "email_results": {
    "success": 1,
    "failed": 0,
    "failed_recipients": []
  },
  "timestamp": "2024-01-01T12:00:00"
}
```

### GET `/health`

헬스 체크

### POST `/validate-emails`

이메일 주소 검증

**요청**
```json
{
  "emails": ["user@example.com", "invalid-email"]
}
```

## 프로젝트 구조

```
backend/
├── main.py              # FastAPI 메인 애플리케이션
├── newsletter_agent.py  # 뉴스레터 생성 에이전트
├── email_utils.py       # 이메일 서비스 및 템플릿
├── requirements.txt     # 의존성 관리
├── .env.example        # 환경 변수 예시
└── README.md           # 이 파일
```

## 기술 스택

- **Framework**: FastAPI
- **AI**: LangChain + OpenAI
- **Email**: Python SMTP
- **Server**: Uvicorn

## 라이선스

MIT License

## 기여

풀 리퀘스트를 환영합니다!
