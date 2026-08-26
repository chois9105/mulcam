@echo off
chcp 65001 >nul
title MySQL 시작
echo ============================================
echo   MySQL 서비스를 시작합니다
echo ============================================
echo.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] 관리자 권한이 필요합니다.
    echo.
    echo 이 파일을 마우스 오른쪽 버튼으로 클릭한 뒤
    echo "관리자 권한으로 실행" 을 선택해 주세요.
    echo.
    pause
    exit /b 1
)

sc query MYSQL84 | find "RUNNING" >nul
if %errorlevel% equ 0 (
    echo MySQL 이 이미 켜져 있습니다.
    goto done
)

echo MySQL 시작 중...
net start MYSQL84
if %errorlevel% neq 0 (
    echo.
    echo [실패] 서비스를 시작하지 못했습니다.
    pause
    exit /b 1
)

:done
echo.
echo ============================================
echo   완료. 이제 창을 닫으셔도 됩니다.
echo ============================================
echo.
echo 다음으로 backend\.env 파일을 열어
echo   MYSQL_PASSWORD=  뒤에 비밀번호를 넣어주세요.
echo.
pause
