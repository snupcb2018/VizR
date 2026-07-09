# Dockerfile (레포 루트)
FROM eclipse-temurin:21-jre-noble

# 환경 변수 설정
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Seoul

# Node.js 설치 (Frontend 빌드용)
RUN apt-get update && apt-get install -y curl gnupg2 ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs

# 기본 패키지 및 RNA-Seq 도구 설치
RUN apt-get update && apt-get install -y --fix-missing \
    bash \
    coreutils \
    python3 \
    python3-venv \
    python3-pip \
    curl \
    wget \
    unzip \
    prinseq-lite \
    hisat2 \
    stringtie \
    samtools \
    sudo \
    vim \
    git \
    redis-server \
    gnupg \
    lsb-release \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc \
 && chmod a+r /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y docker-ce-cli \
 && rm -rf /var/lib/apt/lists/*

# FastQC 수동 설치
RUN cd /opt \
 && wget -q -O FastQC.zip https://www.bioinformatics.babraham.ac.uk/projects/fastqc/fastqc_v0.12.1.zip \
 && unzip -q FastQC.zip \
 && rm FastQC.zip \
 && chmod +x /opt/FastQC/fastqc \
 && ln -s /opt/FastQC/fastqc /usr/local/bin/fastqc

# SRA Toolkit 설치 시도 (선택적)
RUN apt-get update && apt-get install -y --fix-missing sra-toolkit || true \
 && rm -rf /var/lib/apt/lists/*

# Trimmomatic 수동 설치 및 wrapper 스크립트 생성
RUN cd /opt \
 && wget -q http://www.usadellab.org/cms/uploads/supplementary/Trimmomatic/Trimmomatic-0.39.zip \
 && unzip -q Trimmomatic-0.39.zip \
 && rm Trimmomatic-0.39.zip \
 && echo '#!/usr/bin/bash' > /usr/local/bin/trimmomatic \
 && echo '"${JAVA_HOME:-/opt/java/openjdk}/bin/java" -jar /opt/Trimmomatic-0.39/trimmomatic-0.39.jar "$@"' >> /usr/local/bin/trimmomatic \
 && chmod +x /usr/local/bin/trimmomatic

# RNA-Seq 분석 도구 설치 확인
RUN which trimmomatic && trimmomatic -version \
 && which prinseq-lite.pl || echo "PRINSEQ not in PATH" \
 && which hisat2 || echo "HISAT2 not in PATH" \
 && which stringtie || echo "StringTie not in PATH" \
 && which samtools || echo "SAMtools not in PATH" \
 && which fasterq-dump && fasterq-dump --version || echo "SRA Toolkit not in PATH"

RUN mkdir -p /app
RUN mkdir -p /app/frontend/node_modules

WORKDIR /app

# Copy application files
COPY requirements.txt /app/
COPY resource /app/resource
COPY start.sh /app/
COPY config /app/config
COPY backend /app/backend
COPY frontend /app/frontend

# Make start.sh executable
RUN chmod +x /app/start.sh

# Frontend 빌드 (프로덕션 모드용)
# vite.config.ts의 outDir: '../static' 설정에 의해 /app/static에 직접 빌드됨
RUN cd /app/frontend && npm install && npm run build

# Python 패키지 설치
# 가상환경 생성 후 패키지 설치
RUN python3 -m venv /opt/venvs/vizr \
    && /opt/venvs/vizr/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venvs/vizr/bin/pip install --no-cache-dir -r requirements.txt

ENV PATH="/opt/venvs/vizr/bin:${PATH}"

CMD ["/usr/bin/bash", "/app/start.sh"]
