"""
run_streamlit.py
Streamlit 뉴스레터 에이전트 대시보드 실행 런처
"""

import sys
import subprocess
import os

if __name__ == "__main__":
    app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "streamlit_app.py")
    cmd = [sys.executable, "-m", "streamlit", "run", app_path, "--server.port", "8501"]
    print("=" * 65)
    print("🚀 Streamlit 맞춤형 AI 뉴스레터 에이전트 대시보드 실행 중...")
    print("👉 접속 주소: http://localhost:8501")
    print("=" * 65)
    subprocess.run(cmd)
