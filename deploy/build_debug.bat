@echo off
chcp 65001 >nul
REM VizR Debug Version 빌드 스크립트

echo ======================================
echo VizR Debug 버전 빌드 시작
echo ======================================

REM PyInstaller 설치 확인
pip install -r requirements.txt

echo.
echo [정리] 기존 프로세스 종료...

REM 프로세스 강제 종료
taskkill /F /IM VizR_Debug.exe /T 2>nul
timeout /t 2 /nobreak >nul

REM 기존 빌드 폴더 삭제
if exist build rmdir /s /q build 2>nul
if exist dist\VizR_Debug.exe del /f /q dist\VizR_Debug.exe 2>nul
if exist VizR_Debug.spec del /f /q VizR_Debug.spec 2>nul

echo.
echo [빌드] Debug 버전 빌드 중...

REM PyInstaller로 Debug 버전 빌드 (콘솔 창 표시 + 로그 출력)
pyinstaller --onefile ^
    --console ^
    --name VizR_Debug ^
    vizr_launcher_debug.py

echo.
echo ======================================
echo Debug 빌드 완료!
echo ======================================
echo.
echo 실행 파일 위치: dist\VizR_Debug.exe
echo.

REM Copy VizR_Debug.exe to user home directory
echo [복사] VizR_Debug.exe를 C:\Users\hjung로 복사 중...
if exist dist\VizR_Debug.exe (
    copy /Y dist\VizR_Debug.exe C:\Users\hjung\VizR_Debug.exe >nul
    if exist C:\Users\hjung\VizR_Debug.exe (
        echo 복사 완료: C:\Users\hjung\VizR_Debug.exe
    ) else (
        echo [경고] 복사 실패
    )
) else (
    echo [경고] dist\VizR_Debug.exe를 찾을 수 없습니다.
)

echo.
echo 실행 방법: C:\Users\hjung\VizR_Debug.exe 더블클릭
echo 콘솔 창에서 에러 메시지를 확인할 수 있습니다.
echo.
pause
