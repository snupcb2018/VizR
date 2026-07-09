@echo off
chcp 65001 >nul
REM VizR Launcher 실행 파일 빌드 스크립트
REM 사용법: build_exe.bat [출력_디렉토리]
REM 예시: build_exe.bat C:\Temp\VizR_Build

REM 출력 디렉토리 설정 (인수가 없으면 현재 디렉토리의 dist 사용)
set OUTPUT_DIR=%~1
if "%OUTPUT_DIR%"=="" (
    set OUTPUT_DIR=%~dp0
    echo 출력 디렉토리 미지정 - 현재 디렉토리 사용: !OUTPUT_DIR!
) else (
    echo 출력 디렉토리: %OUTPUT_DIR%
)

REM 출력 디렉토리 생성
if not exist "%OUTPUT_DIR%" (
    mkdir "%OUTPUT_DIR%"
    echo 출력 디렉토리 생성: %OUTPUT_DIR%
)

echo ======================================
echo VizR Launcher 빌드 시작
echo ======================================

REM PyInstaller 설치 확인
pip install -r requirements.txt

echo.
echo [정리] 기존 VizR 프로세스 종료 및 빌드 폴더 삭제 중...

REM VizR 프로세스 강제 종료 (실행 중인 경우)
taskkill /F /IM VizR.exe /T 2>nul
taskkill /F /IM VizR_Debug.exe /T 2>nul

REM 프로세스 종료 대기 (5초로 증가)
echo 프로세스 종료 대기 중...
timeout /t 5 /nobreak >nul

REM 기존 빌드 임시 파일만 삭제 (dist 폴더는 유지 - config 파일 보존)
echo 빌드 임시 파일 삭제 중...
if exist "%OUTPUT_DIR%\build" rmdir /s /q "%OUTPUT_DIR%\build" 2>nul
if exist "%OUTPUT_DIR%\VizR.spec" del /f /q "%OUTPUT_DIR%\VizR.spec" 2>nul
if exist "%OUTPUT_DIR%\dist\VizR.exe" (
    echo 기존 VizR.exe 삭제 시도...
    del /f /q "%OUTPUT_DIR%\dist\VizR.exe" 2>nul
    timeout /t 1 /nobreak >nul
    if exist "%OUTPUT_DIR%\dist\VizR.exe" (
        echo [경고] VizR.exe를 삭제할 수 없습니다.
        echo VizR.exe가 실행 중일 수 있습니다. 종료 후 다시 시도해주세요.
        pause
        exit /b 1
    )
)

echo 정리 완료!

REM vizr_launcher.py를 출력 디렉토리로 복사
echo.
echo [복사] vizr_launcher.py를 출력 디렉토리로 복사 중...
copy /Y vizr_launcher.py "%OUTPUT_DIR%\vizr_launcher.py" >nul
if exist "%OUTPUT_DIR%\vizr_launcher.py" (
    echo 복사 완료: %OUTPUT_DIR%\vizr_launcher.py
) else (
    echo [경고] vizr_launcher.py 복사 실패
    pause
    exit /b 1
)

REM 출력 디렉토리로 이동
cd /d "%OUTPUT_DIR%"

REM PyInstaller로 실행 파일 빌드
echo.
echo 빌드 중...

REM Check if logo file exists
set LOGO_PARAM=
if exist vizr_logo.png (
    echo Logo 파일 발견: vizr_logo.png
    set LOGO_PARAM=--add-data "vizr_logo.png;."
) else (
    echo Logo 파일 없음 (텍스트 placeholder 사용)
)

REM Check if version.txt exists
set VERSION_PARAM=
if exist version.txt (
    echo 버전 메타데이터 파일 발견: version.txt
    set VERSION_PARAM=--version-file version.txt
) else (
    echo 버전 메타데이터 파일 없음
)

REM PyInstaller 실행 (현재 디렉토리에서 빌드)
REM AV 오탐 완화: --onefile (단일 파일), --clean (캐시 삭제), --noupx (UPX 비활성화)
pyinstaller --onefile ^
    --clean ^
    --noupx ^
    --name VizR ^
    %LOGO_PARAM% ^
    %VERSION_PARAM% ^
    vizr_launcher.py

echo.
echo ======================================
echo 빌드 완료!
echo ======================================
echo.
echo 실행 파일 위치: %OUTPUT_DIR%\dist\VizR.exe
echo.

REM 원래 디렉토리로 돌아가기
cd /d "%~dp0"

pause
