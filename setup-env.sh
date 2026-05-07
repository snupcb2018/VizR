#!/bin/bash
# VizR 환경 설정 스크립트
# config.json에서 설정을 읽어 .env 파일 생성

echo "🔧 VizR 환경 설정 시작..."

# config.json 파일 존재 확인
if [ ! -f "config.json" ]; then
    echo "❌ config.json 파일이 없습니다."
    echo "📝 기본 config.json 파일을 생성합니다..."
    cat > config.json << 'EOF'
{
  "_comment": "VizR 사용자 설정 파일 - 아래 경로를 본인의 데이터 저장 경로로 변경하세요",
  "vizr_path": "./",
  "environment": "development",
  "log_level": "INFO",
  "ports": {
    "backend": 5001,
    "frontend": 5173
  }
}
EOF
    echo "✅ 기본 config.json 파일이 생성되었습니다."
fi

# Python을 사용하여 config.json 파싱
CONFIG_PATHS=$(python -c "
import json
import os
import sys
from pathlib import Path

try:
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # vizr_path 읽기
    vizr_path = config.get('vizr_path', './')
    
    # workbench 경로를 vizr_path/workbench로 설정
    if vizr_path.endswith('/'):
        workbench_path = vizr_path + 'workbench'
    else:
        workbench_path = vizr_path + '/workbench'
    
    # 두 경로를 공백으로 구분하여 출력
    print(f'{vizr_path}|{workbench_path}')
    
except Exception as e:
    print('Error: ' + str(e), file=sys.stderr)
    sys.exit(1)
" 2>/dev/null)

# 경로들을 분리
VIZR_PATH=$(echo "$CONFIG_PATHS" | cut -d'|' -f1)
VIZR_WORKBENCH_PATH=$(echo "$CONFIG_PATHS" | cut -d'|' -f2)

if [ $? -ne 0 ] || [ -z "$VIZR_WORKBENCH_PATH" ]; then
    echo "❌ config.json 파싱 실패. 기본값을 사용합니다."
    VIZR_PATH="$(pwd)"
    VIZR_WORKBENCH_PATH="$(pwd)/workbench"
fi

echo "📂 VizR 경로: $VIZR_PATH"
echo "📂 워크벤치 경로: $VIZR_WORKBENCH_PATH"

# 경로가 존재하지 않으면 생성
if [ ! -d "$VIZR_WORKBENCH_PATH" ]; then
    echo "📁 워크벤치 디렉토리가 없습니다. 생성합니다..."
    mkdir -p "$VIZR_WORKBENCH_PATH"
    if [ $? -eq 0 ]; then
        echo "✅ 디렉토리 생성 완료: $VIZR_WORKBENCH_PATH"
    else
        echo "❌ 디렉토리 생성 실패: $VIZR_WORKBENCH_PATH"
        exit 1
    fi
else
    echo "✅ 워크벤치 디렉토리 확인됨: $VIZR_WORKBENCH_PATH"
fi

# .env 파일 생성
echo "🌍 .env 파일 생성 중..."
cat > .env << EOF
# VizR 환경변수 (config.json에서 자동 생성됨)
VIZR_PATH=$VIZR_PATH
VIZR_WORKBENCH_PATH=$VIZR_WORKBENCH_PATH
EOF

echo "✅ 환경 설정 완료!"
echo "🚀 이제 'docker compose up'으로 VizR을 시작할 수 있습니다."
echo ""
echo "📋 설정된 경로:"
echo "   VizR 루트: $VIZR_PATH"
echo "   워크벤치: $VIZR_WORKBENCH_PATH"