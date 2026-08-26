# Newsletter Frontend - Remote Backend API 연동판

## 1. 이번 버전에서 삭제되는 로컬 구조

이 버전은 로컬 Agent / 로컬 FastAPI를 사용하지 않습니다.

더 이상 Streamlit에서 다음 파일을 import하거나 호출하지 않습니다.

- agent_graph.py
- cli_agent.py
- main.py
- models.py
- run.py

기존 파일이 같은 폴더에 남아 있어도 실행에는 사용되지 않지만,
혼동 방지를 위해 별도 BACKUP 폴더로 옮기는 것을 권장합니다.

## 2. 새 구조

브라우저
  ↓
Streamlit Frontend : http://localhost:8501
  ↓ HTTPS
Remote Backend     : https://mulcam.1435.co.kr

Swagger 문서:
https://mulcam.1435.co.kr/docs

중요:
`/docs`는 API 문서 화면입니다.
실제 API 호출 Base URL은 `https://mulcam.1435.co.kr` 입니다.

## 3. 연결 API

① 뉴스레터 요청
POST /api/newsletter/request

② 수정 요청
POST /api/drafts/{draft_id}/revise

③ 최종 승인 + 주기 설정
POST /api/drafts/{draft_id}/approve

화면 목록용
GET /api/drafts

상세
GET /api/drafts/{draft_id}

상태 확인
GET /api/status

## 4. Request Body 계약

Frontend와 Backend가 같은 저장소에서 함께 관리되므로 요청 본문은 아래 필드로 고정합니다.

- newsletter request: request_text
- revise: direction
- approve: frequency, approved_template

승인 주기 값:
- every_30_minutes: 30분마다
- hourly: 매시간
- daily: 매일
- weekly: 매주

n8n 발송 연동용 Backend API:
- GET /api/dispatches/pending
  정기 생성됐지만 발송 완료되지 않은 목록을 조회합니다.
- POST /api/dispatches/{draft_id}/result
  외부 메일 API 호출 후 {"sent": true} 또는
  {"sent": false, "error": "실패 사유"}로 결과를 기록합니다.

Backend는 현재 승인 및 정기 생성 단계에서 실제 이메일을 직접 발송하지 않습니다.

Swagger 문서는 연결 상태 확인과 개발 참고용으로 사용합니다.

## 5. 설치

PowerShell:

python -m pip install -r requirements.txt

또는

python -m pip install streamlit requests

## 6. 실행

python run_streamlit.py

또는

python -m streamlit run streamlit_app.py

접속:
http://localhost:8501

## 7. 기존 C:\newsletter_agent\news1 에 적용할 경우

기존 폴더에서 다음 파일만 새 버전으로 교체하면 됩니다.

- streamlit_app.py
- run_streamlit.py

requirements.txt도 함께 두고 requests가 설치되어 있는지 확인하세요.

기존 agent_graph.py/main.py 등은 더 이상 호출하지 않으므로
BACKUP 폴더로 옮기거나 삭제할 수 있습니다.
