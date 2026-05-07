@echo off
chcp 65001 >nul
REM VizR Installer 빌드 스크립트 (Inno Setup)

echo ======================================
echo VizR 설치 프로그램 빌드 시작
echo ======================================

REM 1. VizR.exe 존재 확인
echo.
echo [1/5] VizR.exe 확인 중...
if not exist "dist\VizR.exe" (
    echo [오류] dist\VizR.exe를 찾을 수 없습니다.
    echo 먼저 build_exe.bat를 실행하여 VizR.exe를 빌드해주세요.
    pause
    exit /b 1
)
echo VizR.exe 확인 완료!

REM 2. Inno Setup 컴파일러 찾기
echo.
echo [2/5] Inno Setup 컴파일러 확인 중...
set "ISCC_PATH="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
)
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"
)

if "%ISCC_PATH%"=="" (
    echo [오류] Inno Setup 컴파일러를 찾을 수 없습니다.
    echo.
    echo Inno Setup 6를 다운로드하여 설치해주세요:
    echo https://jrsoftware.org/isdl.php
    echo.
    pause
    exit /b 1
)

echo Inno Setup 찾음: %ISCC_PATH%

REM 3. 출력 디렉토리 생성
echo.
echo [3/5] 출력 디렉토리 준비 중...
if not exist "installer_output" (
    mkdir installer_output
    echo installer_output 폴더 생성
) else (
    echo installer_output 폴더 이미 존재
)

REM 4. Inno Setup 컴파일
echo.
echo [4/5] VizR.iss 컴파일 중...
"%ISCC_PATH%" VizR.iss

if not exist "installer_output\VizR_Setup.exe" (
    echo.
    echo [오류] VizR_Setup.exe 생성 실패
    echo VizR.iss 파일을 확인해주세요.
    pause
    exit /b 1
)

echo.
echo ======================================
echo 설치 프로그램 빌드 완료!
echo ======================================
echo.
echo 생성된 파일: installer_output\VizR_Setup.exe

REM 5. C:\Users\hjung로 복사
echo.
echo [5/5] VizR_Setup.exe를 C:\Users\hjung로 복사 중...
copy /Y installer_output\VizR_Setup.exe C:\Users\hjung\VizR_Setup.exe >nul

if exist C:\Users\hjung\VizR_Setup.exe (
    echo 복사 완료: C:\Users\hjung\VizR_Setup.exe
) else (
    echo [경고] 복사 실패
)

echo.
echo 설치 프로그램 크기:
for %%F in (installer_output\VizR_Setup.exe) do echo %%~zF bytes (약 %%~zF/1048576 MB)

echo.
pause
