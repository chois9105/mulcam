"""
run_streamlit.py
원격 Backend 연동 Streamlit Frontend 실행 런처
"""

import os
import subprocess
import sys


if __name__ == "__main__":
    app_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "streamlit_app.py",
    )

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        app_path,
        "--server.port",
        "8501",
    ]

    print("=" * 68)
    print("Newsletter Streamlit Frontend 시작")
    print("Frontend : http://localhost:8501")
    print("Backend  : https://mulcam.1435.co.kr")
    print("API Docs : https://mulcam.1435.co.kr/docs")
    print("=" * 68)

    subprocess.run(cmd, check=False)
