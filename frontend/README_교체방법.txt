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

## 4. Request Body 자동 대응

현재 실행 환경에서는 원격 Swagger의 실제 Request Body 스키마를 직접 확정할 수 없으므로,
프로그램은 실행 시 다음 URL을 자동으로 읽습니다.

https://mulcam.1435.co.kr/openapi.json

FastAPI OpenAPI 스키마를 읽어 실제 필드명과
뉴스레터 요청 / 수정 요청 / 주기 값을 자동으로 매핑합니다.

OpenAPI를 읽지 못하면 다음 관례적 필드명으로 fallback합니다.

- newsletter request: request_text
- revise: feedback
- approve: frequency

백엔드가 전혀 다른 필수 필드를 요구하면 Streamlit 화면의
"서버 응답 상세"에 FastAPI 422 오류 내용이 표시됩니다.

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
