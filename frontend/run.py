"""
run.py
AgentLetter Pro 원클릭 실행 스크립트
FastAPI 서버를 시작하고 브라우저에서 Apple HIG 대시보드를 자동으로 엽니다.
"""

import sys
import os
import webbrowser
import time
import threading

def start_server():
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, log_level="info")

def open_browser():
    time.sleep(1.2)
    print("\n" + "=" * 65)
    print("🍎 AgentLetter Pro 애플 HIG 대시보드가 브라우저에서 열립니다.")
    print("👉 접속 주소: http://localhost:8000")
    print("📖 API 문서: http://localhost:8000/docs")
    print("=" * 65 + "\n")
    webbrowser.open("http://localhost:8000")

if __name__ == "__main__":
    t = threading.Thread(target=open_browser, daemon=True)
    t.start()
    start_server()
