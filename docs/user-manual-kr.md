<style>
/* ===== 전체 본문 ===== */
body {
    font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
    line-height: 1.8;
    color: #2c3e50;
    max-width: 960px;
    margin: 0 auto;
    padding: 30px 40px;
}

/* ===== 제목 계층 ===== */
h1 {
    color: #0056b3;
    border-bottom: 3px solid #0056b3;
    padding-bottom: 10px;
    margin-top: 50px;
    font-size: 2.2em;
}

h2 {
    color: #2c3e50;
    border-left: 5px solid #0056b3;
    padding: 8px 15px;
    margin-top: 40px;
    background: linear-gradient(to right, #f0f4f8, transparent);
    font-size: 1.6em;
}

h3 {
    color: #34495e;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 6px;
    margin-top: 30px;
    font-size: 1.3em;
}

h4 {
    color: #475569;
    margin-top: 24px;
    font-size: 1.1em;
    font-weight: 600;
}

/* ===== Callout 상자 (참고/주의/해석) ===== */
blockquote {
    background: #f8fafc;
    border-left: 4px solid #64748b;
    padding: 12px 18px;
    margin: 18px 0;
    font-style: normal;
    color: #475569;
    border-radius: 0 6px 6px 0;
}

/* ===== 인라인 코드 ===== */
code {
    background-color: #f1f5f9;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: "Consolas", "D2Coding", monospace;
    font-size: 0.9em;
    color: #be185d;
}

/* ===== 코드 블록 ===== */
pre {
    background-color: #f6f8fa;
    color: #24292e;
    border: 1px solid #d0d7de;
    padding: 16px 20px;
    border-radius: 8px;
    overflow-x: auto;
    line-height: 1.5;
}
pre code {
    background: none;
    color: inherit;
    padding: 0;
    font-size: 0.88em;
}

/* ===== 테이블 ===== */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
    font-size: 0.95em;
}
thead th {
    background-color: #1e3a5f;
    color: #ffffff;
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
}
tbody td {
    border: 1px solid #e2e8f0;
    padding: 9px 14px;
    vertical-align: top;
}
tbody tr:nth-child(even) {
    background-color: #f8fafc;
}
tbody tr:hover {
    background-color: #eef2ff;
}

/* ===== 이미지 ===== */
img {
    display: block;
    margin: 24px auto;
    max-width: 100%;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

/* ===== 수평선 (섹션 구분) ===== */
hr {
    border: none;
    border-top: 1px solid #cbd5e1;
    margin: 32px 0;
}

/* ===== 목록 ===== */
ul, ol {
    padding-left: 24px;
}
li {
    margin-bottom: 4px;
}
li > ul, li > ol {
    margin-top: 4px;
}

/* ===== 볼드/강조 ===== */
strong {
    color: #1e293b;
}

/* ===== 페이지 나누기 (PDF 출력용) ===== */
.page-break {
    page-break-after: always;
}
</style>

# VizR 워크벤치 사용자 매뉴얼

워크벤치는 RNA-Seq 분석의 기본 작업 단위입니다. 이 매뉴얼은 워크벤치 생성 과정과 각 화면의 기능을 안내합니다.

---

## 목차

### Part 1. 워크벤치 생성 가이드

- [Step 1. 기본 설정 (Basic Setup)](#step-1-기본-설정-basic-setup)
  - [1-1. Workbench Name](#1-1-workbench-name)
  - [1-2. Raw Data Source](#1-2-raw-data-source)
  - [1-3. Analysis Species](#1-3-analysis-species)
- [Step 2. 샘플 매핑 (Sample Mapping)](#step-2-샘플-매핑-sample-mapping)
  - [2-1. Data Layout](#2-1-data-layout)
  - [2-2. Available Files](#2-2-available-files-파일-할당)
  - [2-3. Sample Mapping 테이블](#2-3-sample-mapping-테이블)
- [Step 3. 파이프라인 설정 (Pipeline Configuration)](#step-3-파이프라인-설정-pipeline-configuration)
  - [3-1. Reference Genome](#3-1-reference-genome-settings)
  - [3-2. Quality Control](#3-2-quality-control)
  - [3-3. Sequence Cleaning](#3-3-sequence-cleaning)
  - [3-4. Quantification](#3-4-quantification)
  - [3-5. Differential Expression](#3-5-differential-expression)

### Part 2. 화면 안내

- [1. Workbench Overview](#1-workbench-overview-워크벤치-목록) — 워크벤치 목록
- [2. Overview](#2-overview-워크벤치-상세) — 워크벤치 상세 정보, 파이프라인 상태
- [3. Raw Data](#3-raw-data-원시-데이터) — 원시 데이터 파일 현황
- [4. Quality Control](#4-quality-control-품질-관리) — FastQC 품질 분석 결과
- [5. Preprocessing](#5-preprocessing-전처리) — Trimmomatic / PRINSEQ 전처리 결과
- [6. Alignment](#6-alignment-정렬) — HISAT2 / Bowtie2 정렬 결과
- [7. Counts](#7-counts-발현량-데이터) — 발현량 매트릭스 조회/분석
- [8. DEG](#8-deg-differential-expression) — 차등발현 분석 (DESeq2 / edgeR)
- [9. PCA](#9-pca-principal-component-analysis) — 주성분 분석
- [10. Clustering](#10-clustering-analysis) — 클러스터링 (Tree / Mfuzz / WGCNA)
- [11. Heatmap](#11-heatmap) — 히트맵 시각화
- [12. Venn Diagram](#12-venn-diagram) — 벤 다이어그램

---

<div class="page-break"></div>

## Part 1. 워크벤치 생성 가이드

> 워크벤치 생성은 총 3단계로 구성됩니다: **기본 설정 → 샘플 매핑 → 파이프라인 설정**

### Step 1. 기본 설정 (Basic Setup)

대시보드에서 **Create New Workbench** 버튼을 클릭하면 생성 모달이 열립니다.

### 1-1. Workbench Name

분석 프로젝트의 이름을 입력합니다.

- 허용 문자: **영문(A-Z, a-z), 숫자(0-9), 언더스코어(`_`), 하이픈(`-`)**
- 한글, 공백, 특수문자는 자동으로 제거됩니다
- 입력 즉시 중복 여부가 실시간으로 검증됩니다 (녹색 체크 = 사용 가능)

```
예시: Cold_Stress_Experiment, drought-response-2024
```

> ⚠️ **주의**: 워크벤치 이름은 서버 내 디렉토리명으로도 사용되므로, 분석 목적을 알 수 있는 간결한 이름을 권장합니다.

### 1-2. Raw Data Source

데이터 입력 방식을 3가지 탭 중 하나 선택합니다. **선택된 탭의 데이터만** 워크벤치에 사용됩니다.

> ⚠️ **주의**: 여러 탭에 데이터를 입력하더라도, 현재 활성화된 탭의 데이터만 사용됩니다. 다른 탭에 데이터가 있으면 하단 안내 메시지로 알려줍니다.

---

#### (A) Local Upload

로컬 PC에서 FASTQ/FASTA 파일을 직접 업로드합니다.

**지원 형식**: `.fastq`, `.fq`, `.fasta`, `.fa` 및 `.gz` 압축 파일

**사용 방법**:
1. 파일 업로드 영역에 파일을 드래그앤드롭하거나 클릭하여 선택
2. 업로드 진행률이 표시되며, 완료 시 녹색 체크 표시
3. 모든 파일 업로드가 완료되어야 다음 단계 진행 가능

> ⚠️ **주의**: RNA-seq 파일은 보통 1GB 이상입니다. 업로드 중에는 브라우저를 닫지 마세요. 업로드가 완료될 때까지 Next 버튼이 비활성화됩니다.

> ⚠️ **주의**: 모달을 닫으면 업로드된 파일이 모두 삭제됩니다. 실수로 닫지 않도록 주의하세요.

---

#### (B) NCBI BioProject

NCBI SRA에서 BioProject ID로 데이터를 검색하여 가져옵니다.

**사용 방법**:
1. BioProject ID 입력 (예: `PRJNA252931`)
2. **Search** 버튼 클릭
3. 검색 결과 테이블에서 사용할 파일을 체크박스로 선택
4. 레이아웃(SE/PE)이 자동 감지되어 설정됨

**파일 선택 옵션**:
- 상단 체크박스: 전체 선택/해제
- SE/PE 혼합 BioProject의 경우, SE 또는 PE 버튼으로 해당 레이아웃만 일괄 선택 가능

> ⚠️ **주의**: SE(Single-End)와 PE(Paired-End) 파일을 혼합 선택할 수 없습니다. 동일한 레이아웃의 파일만 선택하세요.

> ⚠️ **주의**: Long-read 데이터(PacBio, Nanopore 등)는 자동으로 감지되어 제외됩니다. VizR은 Illumina short-read 데이터만 지원합니다.

---

#### (C) From Server

서버에 이미 존재하는 FASTQ/FASTA 파일을 경로로 지정합니다.

> ⚠️ **주의**: VizR이 인식할 수 있는 파일은 **VizR Data Folder(`/vizr`) 내부로 제한**됩니다. 서버의 다른 위치에 있는 파일은 VizR에서 접근할 수 없으므로, 반드시 VizR Data Folder 안으로 파일을 먼저 복사하거나 이동한 후 경로를 입력해야 합니다.

**파일 경로 입력 방법**:

VizR 설치 시 선택한 **VizR Data Folder** 안에 파일을 배치하면 VizR에서 인식할 수 있습니다.

![Select VizR Data Folder](images/installer/select-vizr-data-folder.png)

Windows 설치 과정에서 VizR는 **VizR Data Folder**를 묻습니다. 이 폴더는 프로그램 설치 경로가 아니라 업로드 파일, 워크벤치 데이터, 중간 산출물, 분석 결과를 저장하는 호스트 폴더입니다. VizR 및 Docker 컨테이너 내부에서는 이 위치가 `/vizr`로 마운트되므로, 서버 경로 입력 방식에서 사용하는 파일 경로는 `/vizr/...`를 기준으로 작성해야 합니다.

> ℹ️ **참고**: VizR Data Folder란 VizR 설치 시 "Select VizR Data Folder" 단계에서 지정한 폴더입니다. Windows 기본값은 `C:\Users\사용자명\Documents\VizR_Data`, Linux 기본값은 `~/VizR_Data`입니다.

VizR 내부에서는 이 폴더가 `/vizr` 경로로 표시됩니다. 따라서 파일 경로를 입력할 때는 `/vizr/`로 시작하는 경로를 사용합니다.

| 내 컴퓨터에서의 실제 위치 | VizR에 입력할 경로 |
|---|---|
| `VizR_Data\raw_data\sample1.fastq.gz` | `/vizr/raw_data/sample1.fastq.gz` |
| `VizR_Data\experiment\sample2.fq.gz` | `/vizr/experiment/sample2.fq.gz` |

**사용 방법**:
1. 분석할 FASTQ 파일을 **VizR Data Folder** 안으로 복사 (하위 폴더 생성 가능)
2. 텍스트 영역에 `/vizr/`로 시작하는 경로를 **한 줄에 하나씩** 입력
3. Next 클릭 시 파일 존재 여부 및 형식이 자동 검증됨

```
예시: VizR Data Folder 안에 raw_data 폴더를 만들고 파일을 넣은 경우

/vizr/raw_data/sample1_R1.fastq.gz
/vizr/raw_data/sample1_R2.fastq.gz
/vizr/raw_data/sample2_R1.fastq.gz
/vizr/raw_data/sample2_R2.fastq.gz
```

> ⚠️ **주의**: VizR Data Folder 밖에 있는 파일은 VizR에서 접근할 수 없습니다. 반드시 해당 폴더 안에 파일을 복사한 후 `/vizr/...` 경로로 입력하세요.

> ⚠️ **주의**: Long-read 데이터가 포함된 경우 검증 단계에서 차단됩니다.

### 1-3. Analysis Species

분석 대상 종을 선택합니다.

- 현재 **Arabidopsis thaliana**만 활성화되어 있습니다
- Lemna, Spirodela, Wolffia 등은 추후 지원 예정입니다

### 1-4. 다음 단계로 이동

모든 항목을 입력한 뒤 **Next** 버튼을 클릭하면 Step 2(Sample Mapping)로 이동합니다.

Next 클릭 시 아래 항목이 자동으로 검증됩니다:
- Workbench Name이 비어있거나 중복인 경우
- 선택한 데이터 소스에 파일이 없는 경우
- Server 경로의 파일이 존재하지 않거나 형식이 올바르지 않은 경우

검증 실패 시 상단에 빨간색 오류 메시지가 표시됩니다. 해당 항목을 수정한 뒤 다시 시도하세요.

---

## Step 2. 샘플 매핑 (Sample Mapping)

업로드한 FASTQ 파일을 실험 그룹과 샘플에 매핑하는 단계입니다.

### 2-1. Data Layout

데이터의 시퀀싱 레이아웃을 선택합니다.

| 레이아웃 | 설명 | 파일 수 |
|---|---|---|
| **Single-End (SE)** | 샘플당 FASTQ 파일 1개 | 1 file/sample |
| **Paired-End (PE)** | 샘플당 Forward + Reverse 파일 2개 | 2 files/sample |

- NCBI 데이터의 경우 Step 1에서 자동 감지된 값이 설정되어 있습니다
- Local Upload / From Server의 경우 직접 선택합니다

> ⚠️ **주의**: 레이아웃을 변경하면 이미 할당된 파일 매핑이 **전부 초기화**됩니다. 확인 팝업이 표시되니 신중하게 변경하세요.

### 2-2. Available Files (파일 할당)

**Available Files** 패널에 매핑 가능한 파일 목록이 표시됩니다. 드래그앤드롭으로 아래 매핑 테이블에 할당합니다.

- 파일을 드래그하여 원하는 행의 드롭 영역에 놓으면 할당 완료
- 할당된 파일 옆 **X** 버튼을 클릭하면 할당 해제되고 Available Files로 복귀
- 모든 파일이 할당되면 "All files have been assigned" 메시지가 표시됩니다

> ⚠️ **주의**: NCBI 데이터 소스를 선택한 경우, 파일이 자동으로 매핑 테이블에 할당되어 있으므로 이 패널은 비어 있습니다. Group Name만 입력하면 됩니다.

### 2-3. Sample Mapping 테이블

각 행이 하나의 샘플을 나타냅니다. 행 수는 파일 수와 레이아웃에 따라 자동 계산됩니다.

| 컬럼 | 입력 방법 | 설명 |
|---|---|---|
| **Group Name** | 직접 입력 | 실험 그룹명 (예: `Control`, `Treatment`, `Cold_6h`) |
| **Replicate** | 직접 입력 | 샘플명 (예: `Rep1`, `Rep2`). 전체에서 고유해야 함 |
| **FASTQ File** (SE) | 드래그앤드롭 | 해당 샘플의 FASTQ 파일 |
| **Forward Read** (PE) | 드래그앤드롭 | Paired-End의 Forward read 파일 (`_1.fastq.gz`) |
| **Reverse Read** (PE) | 드래그앤드롭 | Paired-End의 Reverse read 파일 (`_2.fastq.gz`) |

- **Add Row**: 우측 상단 버튼으로 매핑 행 추가
- **Remove Row**: 각 행 우측 휴지통 아이콘으로 삭제

> ⚠️ **주의**: Group Name이 DEG(차등발현) 분석의 비교 그룹으로 사용됩니다. 동일 조건의 샘플은 반드시 같은 Group Name을 입력하세요.

### 2-4. 다음 단계로 이동

**Next** 클릭 시 아래 항목이 검증됩니다:

- Available Files에 미할당 파일이 남아 있는 경우
- Sample Name(Replicate)이 비어있거나 중복인 경우
- Group Name이 비어있는 경우

검증을 통과하면 Step 3(Pipeline Configuration)으로 이동합니다.

---

## Step 3. 파이프라인 설정 (Pipeline Configuration)

RNA-Seq 분석 파이프라인의 각 단계별 도구와 파라미터를 설정합니다.

### 3-1. Reference Genome Settings

정렬(Alignment) 및 정량화(Quantification)에 사용할 레퍼런스 게놈을 설정합니다.

| 항목 | 설명 |
|---|---|
| **Reference Set** | 레퍼런스 게놈 버전 선택 (예: `TAIR10`). Step 1에서 선택한 종에 따라 목록이 필터링됨 |
| **Species** | Step 1에서 선택한 종이 자동 표시 (읽기 전용) |

> ⚠️ **주의**: 해당 종에 사용 가능한 Reference Set이 없으면 Settings 페이지에서 먼저 업로드해야 합니다.

### 3-2. Quality Control

시퀀싱 데이터의 품질을 평가합니다.

| 도구 | 설명 | 파라미터 |
|---|---|---|
| **FastQC** | Illumina 시퀀싱 데이터 품질 리포트 생성 | `threads`: 처리 스레드 수 (기본값: 4) |
| **Skip QC** | QC 단계 건너뛰기 | 없음 |

### 3-3. Sequence Cleaning

저품질 리드 제거 및 어댑터 트리밍을 수행합니다. 4가지 옵션 중 선택합니다.

#### (A) Skip Cleaning

전처리 없이 원시 데이터를 그대로 사용합니다.

#### (B) Trimmomatic Only

Illumina 어댑터 제거 및 품질 기반 트리밍을 수행합니다.

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `leading` | 3 | 5' 끝 최소 품질 |
| `trailing` | 3 | 3' 끝 최소 품질 |
| `slidingwindow` | 4:15 | 슬라이딩 윈도우 (윈도우 크기:최소 품질) |
| `minlen` | 36 | 최소 리드 길이 |

#### (C) PRINSEQ Only

품질 필터링 및 트리밍을 수행합니다.

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `min_len` | 50 | 최소 시퀀스 길이 |
| `min_qual_mean` | 20 | 최소 평균 품질 점수 |
| `trim_qual_left` | 20 | 5' 끝 품질 기반 트리밍 |
| `trim_qual_right` | 20 | 3' 끝 품질 기반 트리밍 |

#### (D) Trimmomatic → PRINSEQ (Sequential)

Trimmomatic 처리 후 PRINSEQ를 순차 적용합니다. 두 도구의 파라미터를 각각 설정합니다.

이 옵션 선택 시 추가로 **ILLUMINACLIP** 설정이 표시됩니다:

| 항목 | 기본값 | 설명 |
|---|---|---|
| **Adapter** | TruSeq v3 | 어댑터 종류 (TruSeq v3 / TruSeq v2 / Nextera / None) |
| **seed** | 2 | Seed mismatch 허용 수 |
| **palindrome** | 30 | Palindrome clip 임계값 |
| **simple** | 10 | Simple clip 임계값 |

> ⚠️ **주의**: Nextera 어댑터는 Paired-End 전용입니다.

### 3-4. Quantification

리드 정렬 및 유전자 발현량 정량화를 수행합니다.

| 도구 조합 | 설명 | 주요 파라미터 |
|---|---|---|
| **HISAT2 + StringTie** | 스플라이스 정렬 + 전사체 조립 기반 정량화 | `threads` (8), `max_intronlen` (500000), `min_coverage` (2.5), `min_transcript_len` (200) |
| **Bowtie + RSEM** | 고속 정렬 + RSEM 통합 정량화 | `threads` (4), `max_mismatches` (2) |
| **Bowtie2 + RSEM** | 민감 정렬 + RSEM 통합 정량화 | `threads` (4), `preset` (sensitive / very-fast / fast / very-sensitive) |

> ℹ️ **참고**: Bowtie/Bowtie2 + RSEM을 선택하면 정렬과 정량화가 통합 처리되므로, 별도의 Count 단계는 자동으로 비활성화됩니다.

### 3-5. Differential Expression

차등발현 유전자(DEG) 분석을 수행합니다.

| 도구 | 설명 | 파라미터 |
|---|---|---|
| **edgeR** | 디지털 유전자 발현 데이터의 경험적 분석 | `fdr`: False Discovery Rate (기본값: 0.05), `logfc`: Log Fold Change 임계값 (기본값: 1) |

### 3-6. 워크벤치 생성

모든 설정을 확인한 뒤 **Create Workbench** 버튼을 클릭하면 워크벤치가 생성됩니다.

- 생성이 완료되면 모달이 자동으로 닫히고 해당 워크벤치 페이지로 이동합니다
- 생성 중에는 버튼이 "Creating..." 상태로 변경되며 중복 클릭이 방지됩니다
- 실패 시 오류 메시지가 표시됩니다. 내용을 확인하고 수정한 뒤 재시도하세요

> ℹ️ **참고**: 워크벤치 생성은 설정 저장만 수행합니다. 실제 분석 파이프라인 실행은 워크벤치 상세 페이지에서 **Start Analysis** 버튼으로 별도 시작합니다.

---

<div class="page-break"></div>

## Part 2. 화면 안내

### 1. Workbench Overview (워크벤치 목록)

로그인 후 표시되는 메인 화면으로, 생성된 워크벤치 목록을 조회합니다.

#### 화면 구성

| 영역 | 설명 |
|---|---|
| **워크벤치 테이블** | 기존 워크벤치를 Name, Status, Created At, Last Updated 컬럼으로 표시. 행 클릭 시 상세 페이지로 이동 |
| **빈 상태 안내** | 워크벤치가 없을 경우 생성 안내 메시지 표시 |

#### 버튼

| 버튼 | 설명 |
|---|---|
| **Create Workbench** | 우측 상단. 워크벤치 생성 모달 열기 (→ Step 1) |
| **Create Your First Workbench** | 워크벤치가 없을 때 화면 중앙에 표시. 동일 기능 |

---

### 2. Overview (워크벤치 상세)

워크벤치를 클릭하면 표시되는 상세 화면입니다. 워크벤치 정보, 파이프라인 상태, 데이터 요약, 파이프라인 구성을 한눈에 확인할 수 있습니다.

#### 헤더 영역

워크벤치의 기본 정보를 표시합니다.

| 항목 | 설명 |
|---|---|
| **워크벤치 이름** | 생성 시 입력한 이름 |
| **Species** | 분석 대상 종 |
| **Created / Updated** | 생성 및 마지막 업데이트 일시 |
| **Created by** | 생성자 이름 |

**헤더 버튼**:

| 버튼 | 설명 |
|---|---|
| **Share** | 다른 사용자에게 워크벤치 공유. 공유받은 사용자는 읽기 전용으로 결과 열람 가능 |
| **Edit Pipeline** | 파이프라인 설정 수정. 파이프라인 실행 중에는 비활성화 |
| **Delete** | 워크벤치 삭제 |

> ℹ️ **참고**: 공유받은 사용자(Shared User)는 Share 버튼이 **Leave**로 표시되며, Edit Pipeline과 Delete 버튼은 비활성화됩니다.

#### Pipeline Status 영역

현재 파이프라인 실행 상태를 표시합니다.

| 상태 | 설명 |
|---|---|
| **Not Started** | 아직 분석을 시작하지 않은 상태 |
| **Pipeline Starting** | 파이프라인 시작 준비 중 |
| **Pipeline Running** | 분석 진행 중. 진행률 바와 현재 단계 표시 |
| **Pipeline Completed** | 모든 분석 단계 완료 |
| **Pipeline Failed** | 분석 실패. 오류 메시지 표시 |

- 진행률 바: 완료된 단계 수 / 전체 단계 수 (예: 1/4 steps)
- 시작 시간 및 완료 시간 표시

**파이프라인 버튼**:

| 버튼 | 설명 |
|---|---|
| **Start Analysis** | 파이프라인 실행 시작. 이미 실행 중이면 비활성화 |
| **Stop Analysis** | 실행 중인 파이프라인 중지. 실행 중일 때만 활성화 |

#### Data Overview 영역

워크벤치의 데이터 요약 정보를 카드 형태로 표시합니다.

| 카드 | 설명 |
|---|---|
| **Data Layout** | 시퀀싱 레이아웃 (Single-End 또는 Paired-End) |
| **Samples** | 매핑된 샘플 수 |
| **Files** | 원시 데이터 파일 수 |

#### Pipeline Steps 영역

설정된 파이프라인 단계를 순서대로 카드로 표시합니다. 각 카드에는 단계 번호, 설명, 사용 도구가 표시됩니다.

```
예시: ① Data Download (data_downloader) → ② Alignment (hisat2) → ③ Quantification (stringtie) → ④ DEG (edger)
```

> ℹ️ **참고**: 파이프라인 단계 구성은 워크벤치 생성 시 Step 3에서 설정한 내용이 반영됩니다. 변경이 필요하면 **Edit Pipeline** 버튼을 사용하세요.

---

### 3. Raw Data (원시 데이터)

파이프라인 실행 시 데이터 다운로드/복사 진행 상황과 데이터 소스 정보, 샘플 매핑 정보를 확인하는 화면입니다.

#### Real-time File Progress 영역

파일 다운로드(또는 복사) 진행 상황을 실시간으로 모니터링합니다. WebSocket을 통해 자동 업데이트됩니다.

**요약 카드**:

| 카드 | 설명 |
|---|---|
| **Total Files** | 전체 파일 수 |
| **Downloading** | 현재 다운로드 중인 파일 수 |
| **Completed** | 다운로드 완료된 파일 수 |
| **Connection** | WebSocket 연결 상태 (Live / Connecting / Offline) |

**개별 파일 진행률**:

요약 카드 아래에 각 파일의 진행 상태가 카드 형태로 표시됩니다.

| 항목 | 설명 |
|---|---|
| **파일명** | 다운로드 대상 파일 이름 |
| **Status** | 파일 상태 (pending / downloading / completed / compressed / failed) |
| **진행률** | 퍼센트 및 다운로드 크기 / 전체 크기 표시 |
| **진행 바** | 다운로드 시작 전에는 스피너, 시작 후에는 진행률 바로 전환 |

> ℹ️ **참고**: 파이프라인이 아직 시작되지 않았거나 다운로드 단계가 아닌 경우, "Loading file information..." 메시지가 표시됩니다.

#### Data Source Information 영역

워크벤치 생성 시 설정한 데이터 소스 정보를 표시합니다.

| 항목 | 표시 조건 | 설명 |
|---|---|---|
| **Input Method** | 항상 | 데이터 입력 방식 (local upload / ncbi / server) |
| **NCBI BioProject** | NCBI 소스일 때 | BioProject ID (예: PRJNA252931) |
| **Server Paths** | Server 소스일 때 | 설정된 서버 경로 수 |
| **Layout Type** | 항상 | 시퀀싱 레이아웃 (Paired-End 또는 Single-End) |

#### Sample Mapping Information 영역

워크벤치 생성 시 Step 2에서 설정한 샘플 매핑 정보를 테이블로 표시합니다.

| 컬럼 | 설명 |
|---|---|
| **Group** | 실험 그룹명 |
| **Sample** | 샘플명 |
| **Forward Read** | Forward read 파일명 |
| **Reverse Read** | Reverse read 파일명 (Paired-End일 때만 표시) |

> ℹ️ **참고**: 이 테이블은 읽기 전용입니다. 샘플 매핑을 수정하려면 새 워크벤치를 생성해야 합니다.

---

### 4. Quality Control (품질 관리)

FastQC 기반 시퀀싱 데이터 품질 분석 결과를 확인하는 화면입니다. 파이프라인 진행 상태에 따라 화면 구성이 달라집니다.

> ℹ️ **참고**: 워크벤치 생성 시 QC 단계를 "Skip QC"로 설정한 경우, 이 탭은 비활성화 메시지가 표시됩니다.

#### 분석 상태별 화면

| 상태 | 화면 내용 |
|---|---|
| **Not Started / Pending** | 데이터 다운로드 완료 대기 메시지 |
| **Running** | 분석 진행률 표시 (완료 파일 수 / 전체 파일 수, 진행률 바) |
| **Completing** | 분석 완료 축하 메시지 (약 3.5초 후 결과 화면으로 자동 전환) |
| **Completed** | QC 결과 대시보드 (아래 상세 설명) |

#### 완료 상태 - 결과 대시보드

분석이 완료되면 좌측 사이드바 + 우측 메인 영역 레이아웃으로 전환됩니다.

**좌측 사이드바**:

| 항목 | 설명 |
|---|---|
| **Overview** | 전체 샘플 요약 화면으로 이동 |
| **샘플 목록** | 각 샘플이 품질 상태 배지(녹색=Passed, 노란색=Warning, 빨간색=Failed)와 함께 표시됨. 클릭 시 해당 샘플 상세 화면으로 이동 |

각 샘플 항목에는 총 시퀀스 수(Total Sequences)와 평균 품질(Avg Quality)이 함께 표시됩니다.

**우측 메인 영역 - Overview 선택 시**:

| 영역 | 설명 |
|---|---|
| **Module Statistics** | Total Samples, Total Modules, Passed/Warning/Failed Modules 요약 카드 |
| **Sample Cards** | 전체 샘플을 카드 그리드로 표시. 각 카드에 샘플명, 상태(PASS/WARN/FAIL), 그룹, Total Sequences, Avg Length, Avg Quality 정보 포함. 카드 클릭 시 상세 화면으로 이동 |

**우측 메인 영역 - 개별 샘플 선택 시**:

3개 레이어로 구성됩니다.

**Layer 1. 핵심 지표 요약**:
- **Summary Statistics**: Total Sequences, Average Length, Average Quality, Sample ID
- **Module Statistics**: FastQC 모듈별 Pass/Warn/Fail 상태 테이블
- **Quick Summary**: AI 분석 결과 요약 (설정에서 활성화한 경우)

**Layer 2. AI 품질 분석** (Detailed Quality Analysis):
- AI 모델이 분석한 품질 평가, 우려 사항, 권장 사항을 마크다운 형식으로 표시
- Settings에서 AI 분석 기능이 비활성화된 경우 해당 안내 메시지 표시

**Layer 3. Quality Metrics 차트**:

FastQC 모듈별 시각화 차트입니다. 각 차트 상단에 모듈 상태(Pass/Warn/Fail)가 표시됩니다.

| 차트 | 설명 |
|---|---|
| **Per Base Sequence Quality** | 리드 위치별 품질 점수 분포 |
| **Per Sequence Quality Scores** | 시퀀스별 평균 품질 점수 분포 |
| **Per Base Sequence Content** | 리드 위치별 A/T/G/C 비율 |
| **Per Sequence GC Content** | 시퀀스별 GC 함량 분포 |
| **Per Base N Content** | 리드 위치별 N(미확인 염기) 비율 |
| **Sequence Length Distribution** | 시퀀스 길이 분포 |
| **Adapter Content** | 어댑터 시퀀스 오염 비율 |
| **Sequence Duplication Levels** | 시퀀스 중복 수준 |

> ℹ️ **참고**: 데이터가 없는 모듈의 차트는 자동으로 숨겨집니다.

---

### 5. Preprocessing (전처리)

Trimmomatic 및 PRINSEQ를 사용한 시퀀스 전처리 결과를 확인하는 화면입니다. 상단 서브 탭으로 두 도구 간 전환합니다.

> ℹ️ **참고**: 워크벤치 생성 시 Sequence Cleaning을 "Skip Cleaning"으로 설정한 경우, 해당 도구 탭에 비활성화 메시지가 표시됩니다. 설정한 도구만 활성화됩니다.

#### 서브 탭

| 탭 | 설명 |
|---|---|
| **Trimmomatic** | Trimmomatic 전처리 진행 상황 및 결과 |
| **PRINSEQ** | PRINSEQ 전처리 진행 상황 및 결과 |

각 탭 옆에 상태 인디케이터가 표시됩니다 (회색=Pending, 녹색 깜빡임=Running, 녹색=Completed, 빨간색=Failed). 파이프라인 실행 중에는 현재 진행 중인 도구의 탭으로 자동 전환됩니다.

#### Trimmomatic 탭

**공통 영역**:
- 헤더: 도구명, WebSocket 연결 상태 (Live/Offline), 분석 상태 배지
- 진행률 바: 완료 파일 수 / 전체 파일 수, 퍼센트

**완료 시 결과 영역**:

요약 통계 카드:

| 카드 | 설명 |
|---|---|
| **Total Samples** | 처리된 샘플 수 |
| **Input Reads** | 입력 리드 총 수 |
| **Surviving Reads** | 품질 필터 통과 리드 수 |
| **Survival Rate** | 평균 생존율 (%) |

샘플별 결과 카드: 각 샘플의 Input Reads, Surviving, Removed 수치와 생존율 바가 표시됩니다. 생존율에 따라 색상이 달라집니다 (90% 이상=녹색, 80% 이상=노란색, 80% 미만=빨간색).

#### PRINSEQ 탭

Trimmomatic과 동일한 레이아웃입니다.

**완료 시 결과 영역**:

요약 통계 카드:

| 카드 | 설명 |
|---|---|
| **Total Samples** | 처리된 샘플 수 |
| **Input Sequences** | 입력 시퀀스 총 수 |
| **Good Sequences** | 품질 통과 시퀀스 수 |
| **Quality Rate** | 평균 품질 통과율 (%) |

샘플별 결과 카드: 각 샘플의 Input Sequences, Good Sequences, Bad Sequences 수치가 표시됩니다. 길이 필터링(Length Filtered) 및 품질 필터링(Quality Filtered) 수치도 해당 시 함께 표시됩니다. 품질 통과율에 따라 색상이 달라집니다 (95% 이상=녹색, 90% 이상=노란색, 90% 미만=빨간색).

---

### 6. Alignment (정렬)

레퍼런스 게놈에 대한 리드 정렬(Alignment) 결과를 확인하는 화면입니다.

#### 화면 구성

**헤더 영역**:

| 항목 | 설명 |
|---|---|
| **Read Alignment** | 화면 제목 |
| **도구 배지** | 사용된 정렬 도구명 표시 (예: HISAT2) |
| **WebSocket 상태** | 실시간 연결 상태 (Live/Offline) |
| **Status 배지** | 분석 상태 (Not Started / Pending / Running / Completed / Failed) |

**진행률 바**: 완료 파일 수 / 전체 파일 수, 퍼센트 표시

#### 완료 시 결과 영역

요약 통계 카드:

| 카드 | 설명 |
|---|---|
| **Overall Mapping Rate** | 전체 정렬률 (%) |
| **Total Reads** | 입력 리드 총 수 (백만 단위) |
| **Mapped Reads** | 레퍼런스에 정렬된 리드 수 (백만 단위) |
| **Unmapped Reads** | 정렬되지 않은 리드 수 (백만 단위) |

샘플별 결과 카드: 각 샘플의 Total Reads, Mapped Reads, Unmapped Reads 수치와 정렬률 바가 표시됩니다. Multi-mapped Reads가 있는 경우 추가로 표시됩니다. 정렬률에 따라 색상이 달라집니다 (90% 이상=녹색, 80% 이상=노란색, 80% 미만=빨간색).

> ℹ️ **참고**: 정렬률이 80% 미만인 샘플은 데이터 품질이나 레퍼런스 적합성을 재검토할 필요가 있습니다.

---

### 7. Counts (발현량 데이터)

유전자 발현량 정량화(Quantification) 결과를 조회, 검색, 분석하는 인터랙티브 화면입니다.

> ℹ️ **참고**: 이 화면은 정량화가 완료된 후에만 데이터가 표시됩니다. 완료 전에는 진행률 바와 대기 메시지가 표시됩니다.

#### 1. 매트릭스 타입 선택

우측 상단의 버튼 그룹으로 발현량 데이터 타입을 전환합니다.

| 타입 | 설명 |
|---|---|
| **Gene Count** (Raw) | 유전자 수준 원시 리드 카운트 |
| **TPM** | Transcripts Per Million 정규화 |
| **TMM** | Trimmed Mean of M-values 정규화 (기본값) |

- 타입 변경 시 테이블이 자동으로 새로고침됩니다
- 타입 변경 시 검색어와 패턴 분석 상태가 초기화됩니다

#### 2. 유전자 검색

좌측 상단의 검색 영역에서 유전자를 검색할 수 있습니다.

**사용 방법**:
1. 검색창에 Gene ID 또는 Gene Symbol을 입력
2. 여러 유전자를 동시에 검색하려면 **쉼표, 공백, 탭, 줄바꿈**으로 구분하여 입력
3. **Search** 버튼 클릭 또는 `Ctrl+Enter`로 검색 실행
4. **Clear** 버튼으로 검색 초기화 (전체 데이터로 복귀)

```
예시: AT1G01010, AT1G01020, AT1G01030
```

검색이 활성화되면 테이블 상단에 파란색 정보 바가 표시되어 검색 결과 유전자 수를 알려줍니다.

#### 3. Pattern-Based Gene Selection (패턴 기반 유전자 선택)

특정 발현 패턴을 보이는 유전자를 자동으로 탐색하는 기능입니다. 접기/펼치기 패널로 구현되어 있습니다.

**오디오 이퀄라이저 UI**:

각 실험 그룹(조건)에 대해 기대하는 상대적 발현 수준을 슬라이더로 설정합니다(0~10 스케일). 예를 들어 Control=2, Treatment_6h=5, Treatment_24h=8로 설정하면 시간에 따라 발현이 증가하는 패턴의 유전자를 검색합니다.

**프리셋**:

| 프리셋 | 설명 |
|---|---|
| **Weak Up** | 약한 상향 조절 패턴 (3→6) |
| **Strong Up** | 강한 상향 조절 패턴 (2→9) |
| **Weak Down** | 약한 하향 조절 패턴 (6→3) |
| **Strong Down** | 강한 하향 조절 패턴 (9→2) |
| **Custom** | 사용자 직접 설정 |

각 그룹은 개별적으로 비활성화(OFF)할 수 있으며, 비활성화된 그룹은 분석에서 제외됩니다.

**통계 임계값** (Statistical Thresholds):

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| **Min Spearman Correlation** | 0.6 | 설정한 패턴과의 최소 상관계수 (높을수록 엄격) |
| **Min Log2 Fold Change** | 1.0 | 그룹 간 최소 발현 변화량 |
| **Min CPM** | 0 | 최소 1개 그룹에서의 최소 발현 수준 (Counts Per Million) |

**제약 허용치** (Constraint Tolerances):

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| **Equality Tolerance** | 0.3 | 동일 수준으로 설정된 그룹 간 허용 차이 (log2 스케일) |
| **Order Gap** | 0.5 | 순서가 다른 그룹 간 최소 차이 (log2 스케일) |

**CV 필터** (선택 사항, 토글로 활성화):

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| **Max CV** | 0.5 | 그룹 내 최대 변이 계수 (SD/mean) |
| **Min Groups Pass CV** | 1 | CV 임계값을 통과해야 하는 최소 그룹 수 |

**Equality Constraints** (선택 사항):

유사한 발현 수준을 가져야 하는 그룹 쌍을 지정합니다. 두 그룹을 선택하고 **Add** 버튼으로 추가합니다.

**실행**:
- 최소 2개 이상의 활성 그룹이 있어야 **Analyze Pattern** 버튼이 활성화됩니다
- 분석 결과 매칭된 유전자가 테이블에 표시됩니다
- 결과가 없으면 임계값 조정을 권장하는 안내 모달이 표시됩니다
- **Reset All** 버튼으로 모든 설정을 초기화할 수 있습니다

> ⚠️ **주의**: 패턴 분석이 활성화된 상태에서 검색을 하면 패턴 결과 내에서만 검색됩니다. 전체 데이터로 돌아가려면 정보 바의 **Reset to all genes** 링크를 클릭하세요.

#### 4. 발현량 테이블

유전자 발현량 데이터를 테이블 형태로 표시합니다.

**테이블 컬럼**:

| 컬럼 | 설명 | 조작 |
|---|---|---|
| **체크박스** | 유전자 선택/해제 | 개별 클릭 또는 헤더의 전체 선택 체크박스 사용 |
| **Gene ID** | 유전자 식별자 (예: AT1G01010) | 마우스 호버 시 Gene Description 툴팁 표시 |
| **Gene Symbol** | 유전자 심볼 (예: NHX1) | Gene ID와 다를 때만 이탤릭체로 표시 |
| **Expression Pattern** | 미니 히트맵 시각화 | 해당 유전자의 전체 샘플 발현 패턴을 색상으로 표현 |
| **샘플 컬럼** | 각 샘플의 발현량 수치 | 컬럼 헤더 클릭 시 해당 컬럼 하이라이트 (파란색 배경) |

- Gene ID, Gene Symbol 컬럼은 좌측에 고정(Sticky)되어 가로 스크롤 시에도 항상 표시됩니다
- 테이블 높이는 브라우저 뷰포트에 맞게 자동 조절됩니다

#### 5. 페이지네이션

테이블 상단에 페이지 네비게이션이 표시됩니다.

| 항목 | 설명 |
|---|---|
| **Rows per page** | 페이지당 행 수 선택 (100 / 500 / 1000 / 2000 / 5000) |
| **표시 범위** | 현재 표시 중인 행 범위 (예: 1-500 of 27,416) |
| **페이지 번호** | 클릭하여 해당 페이지로 이동. 7페이지 초과 시 축약 표시 |
| **Previous / Next** | 이전/다음 페이지로 이동 |

#### 6. 유전자 선택 후 분석 (Analyze 메뉴)

테이블에서 유전자를 체크박스로 선택한 후, **Analyze (N)** 드롭다운 버튼을 클릭하면 다음 분석을 실행할 수 있습니다.

| 분석 | 설명 |
|---|---|
| **Heatmap** | 선택된 유전자의 발현량 히트맵 시각화 |
| **GO Enrichment** | Gene Ontology 기능 분석 (BP/MF/CC) |
| **KEGG Pathway** | KEGG 경로 분석 |
| **Venn Diagram** | 벤 다이어그램 비교 |

> ℹ️ **참고**: 유전자를 1개 이상 선택해야 Analyze 버튼이 활성화됩니다. 괄호 안의 숫자는 현재 선택된 유전자 수입니다.

#### 7. 다운로드

**Download** 버튼(녹색)을 클릭하면 현재 매트릭스 타입의 발현량 데이터를 파일로 다운로드합니다.

- 검색이 활성화된 경우 필터링된 결과만 다운로드됩니다 (버튼에 "Filtered" 표시)
- 검색이 없는 경우 전체 데이터가 다운로드됩니다

<div class="page-break"></div>

### 8. DEG (Differential Expression)

차등발현유전자(DEG) 분석 결과를 탐색하는 화면입니다. DESeq2 또는 edgeR로 수행된 분석 결과를 다양한 시각화와 테이블로 확인할 수 있습니다.

#### 1. 분석 상태

DEG 화면 진입 시 파이프라인 상태에 따라 다른 화면이 표시됩니다.

| 상태 | 화면 |
|---|---|
| **not_started** | "No DEG Results Available" - 파이프라인에서 DEG 분석을 먼저 실행하라는 안내 |
| **pending / running** | 스피너와 함께 "Analysis in Progress" 메시지. 사용한 분석 도구명(DESeq2/edgeR) 표시. 5초 간격으로 상태 자동 갱신 |
| **failed** | "Analysis Failed" - 파이프라인 로그 확인 또는 재실행 안내 |
| **insufficient_replicates** | DESeq2 전용 경고. 그룹당 최소 2개의 biological replicate 필요. 현재 샘플 구조(그룹명과 샘플 수)를 함께 표시하며, edgeR 사용 또는 replicate 추가를 권장 |
| **completed** | 분석 결과 대시보드 표시 (아래 상세 설명) |

> ⚠️ **주의**: `insufficient_replicates` 상태는 DESeq2에서만 발생합니다. 그룹당 replicate가 1개인 경우 edgeR를 사용하면 분석이 가능합니다.

#### 2. 화면 구성 (completed 상태)

분석이 완료되면 다음과 같은 레이아웃으로 표시됩니다.

**헤더 영역**:
- "Differential Expression Analysis" 제목
- 사용된 분석 도구 배지 (DESEQ2 또는 EDGER, 보라색 배지)

**좌측 사이드바: Comparisons**

비교 조건 목록이 표시됩니다. 워크벤치에 설정된 그룹 조합(예: Treatment_vs_Control)별로 버튼이 나열됩니다.

- 선택된 비교 조건은 파란색 배경으로 강조
- 각 버튼에 비교 조건명과 분석 도구명이 표시
- 비교 조건을 변경하면 선택된 유전자가 자동으로 초기화됨
- Expression Matrix 탭에서는 사이드바가 숨겨짐 (비교 조건과 무관하므로)

**우측 컨텐츠: 탭 네비게이션**

5개의 탭이 제공됩니다:

| 탭 | 설명 |
|---|---|
| **Matrix (Up)** | 상향조절 유전자(logFC > 0, FDR < 0.05) 테이블 |
| **Matrix (Down)** | 하향조절 유전자(logFC < 0, FDR < 0.05) 테이블 |
| **MA Plot** | 평균 발현량(logCPM) vs 변화량(logFC) 산점도 |
| **Volcano Plot** | 변화량(logFC) vs 통계적 유의성(-log10 p-value) 산점도 |
| **Expression Matrix** | P-value/Fold-change 기준 필터링된 발현 매트릭스 |

> ℹ️ **참고**: 탭을 전환하면 선택된 유전자가 초기화됩니다. 탭 간 유전자 선택은 유지되지 않습니다.

#### 3. Matrix (Up) / Matrix (Down) 탭

상향조절(Up) 또는 하향조절(Down) 유전자만 필터링하여 테이블로 표시합니다. 두 탭의 구조와 기능은 동일하며, 필터링 기준만 다릅니다.

**툴바 영역** (테이블 상단):

| 요소 | 설명 |
|---|---|
| **Search** | Gene ID 또는 Gene Symbol 검색. textarea로 다수의 유전자를 쉼표/공백/탭/줄바꿈으로 구분하여 입력 가능. `Ctrl+Enter`로 검색 실행 |
| **Search 버튼** | 검색 실행 |
| **Clear 버튼** | 검색어가 있을 때만 표시. 검색 초기화 |
| **Analyze 버튼** | 선택된 유전자에 대한 분석 드롭다운 (괄호 안에 선택 수 표시). 유전자 미선택 시 비활성화 |
| **Download 버튼** | TSV 형식으로 다운로드. 선택된 유전자가 있으면 해당 유전자만, 없으면 현재 페이지 전체 |
| **Pagination** | Rows per page (100/500/1000/2000/5000), 페이지 번호, Previous/Next |

**Analyze 드롭다운 메뉴** (Matrix Up/Down 탭):

| 분석 | 설명 |
|---|---|
| **Heatmap** | 선택된 유전자의 발현량 히트맵 |
| **GO Enrichment** | Gene Ontology 기능 분석 (BP/MF/CC) |
| **KEGG Pathway** | KEGG 경로 분석 |
| **Venn Diagram** | 선택된 유전자 세트의 벤 다이어그램 비교 |

**데이터 테이블**:

| 컬럼 | 설명 |
|---|---|
| **Checkbox** | 유전자 선택 (개별/전체 선택). 고정 컬럼(sticky) |
| **Gene ID** | 유전자 ID. 마우스 호버 시 Gene Description 툴팁 표시. 고정 컬럼 |
| **Gene Symbol** | 유전자 심볼 (이탤릭체). Gene ID와 동일한 경우 일반 텍스트. 고정 컬럼 |
| **Expression Pattern** | TMM 정규화 값 기반 MiniHeatmap. 샘플별 발현 패턴을 색상 막대로 시각화 |
| **logFC** | Log2 Fold Change. 필터/정렬 가능 (컬럼 헤더의 필터 아이콘 클릭) |
| **logCPM** | Log2 Counts Per Million. 필터/정렬 가능 |
| **PValue** | 원시 P-value (과학적 표기법). 필터/정렬 가능 |
| **FDR** | False Discovery Rate (과학적 표기법). 필터/정렬 가능 |

**컬럼 필터 & 정렬 기능**:

logFC, logCPM, PValue, FDR 컬럼 헤더 우측의 슬라이더 아이콘을 클릭하면 **Filter & Sort 팝업**이 열립니다.

*정렬 옵션*:

| 옵션 | 설명 |
|---|---|
| **Ascending** | 오름차순 (작은 값 → 큰 값) |
| **Descending** | 내림차순 (큰 값 → 작은 값) |

*값 필터 옵션 (Filter by Value)*:

| 연산자 | 의미 | 예시 |
|---|---|---|
| **Greater than (>)** | 입력값 초과 | logFC > 2 |
| **Greater than or equal (≥)** | 입력값 이상 | logFC ≥ 1 |
| **Less than (<)** | 입력값 미만 | FDR < 0.01 |
| **Less than or equal (≤)** | 입력값 이하 | PValue ≤ 0.05 |
| **Equal to (=)** | 입력값과 일치 | logCPM = 0 |

연산자 선택 시 숫자 입력 필드가 나타나며 소수점 값 입력이 가능합니다. **Apply** 버튼으로 적용, **Clear** 버튼으로 해당 컬럼의 필터와 정렬을 모두 초기화합니다.

*활성 상태 표시*:
- 필터 적용 중: 아이콘 우상단에 파란색 점 (pulse 애니메이션)
- 정렬 적용 중: 컬럼명 옆에 ↑ / ↓ 화살표, 아이콘 파란색으로 변경

> ℹ️ **참고**: 필터와 정렬은 서버사이드로 동작합니다. 필터를 적용하면 전체 데이터에서 조건에 맞는 결과를 다시 조회합니다.

> ℹ️ **참고**: 여러 컬럼에 동시에 필터를 적용할 수 있으며 조건은 **AND**로 결합됩니다. 예: `logFC > 2` AND `FDR < 0.01` 조건을 동시에 설정하면 두 조건을 모두 만족하는 유전자만 표시됩니다.

**다운로드 파일 형식**:
- 형식: TSV (Tab-Separated Values)
- 파일명 예: `Treatment_vs_Control_up_regulated_selected_25_2026-02-13.tsv`
- 포함 컬럼: GeneID, GeneSymbol, logFC, logCPM, PValue, FDR

#### 4. Volcano Plot 탭

logFC(x축) vs -log10(p-value)(y축)을 산점도로 시각화합니다.

**차트 영역**:

| 요소 | 설명 |
|---|---|
| **제목** | "Volcano Plot: {비교 조건명}" |
| **차트 표시 제한** | 우측 상단 드롭다운으로 차트에 표시할 유의 유전자 수 선택: Top 100 / 300 / 500 / 1,000 / 2,000 / All |
| **통계 요약** | Total genes, Upregulated (빨간색), Downregulated (파란색) 수 표시 |
| **X축** | Log Fold Change (logFC) |
| **Y축** | -log10(p-value) |
| **임계선** | 세로 점선 2개: logFC = 1 (FC > 2), logFC = -1 (FC < 0.5). 가로 점선 1개: p-value = 0.05 |

**점 색상 구분**:

| 색상 | 조건 | 크기 |
|---|---|---|
| **빨간색** | 유의 + logFC > 1 (상향조절) | 큰 점 |
| **파란색** | 유의 + logFC < -1 (하향조절) | 큰 점 |
| **주황색** | 유의하지만 |logFC| ≤ 1 | 중간 점 |
| **회색** | 비유의 | 작은 점 (반투명) |

**툴팁** (점 호버 시):
- Gene Symbol (이탤릭체), Gene ID
- logFC, -log10(p-value), FDR 값
- 유의성 상태 (Upregulated/Downregulated/Significant/Not significant)
- 유의 유전자의 경우 Expression Pattern MiniHeatmap 추가 표시

**Interpretation 패널** (차트 하단):
- 차트 해석 가이드 텍스트
- 차트 표시 제한이 전체 유의 유전자보다 적은 경우 Note 표시 (예: "Chart displays top 100 significant genes. All 1,234 significant genes are available in the table below.")
- Significant / Up / Down 수치 요약

**Significant Genes Table** (차트 아래):

Volcano Plot 탭의 테이블은 FDR < 0.05인 유의 유전자만 표시합니다.

| 컬럼 | 설명 |
|---|---|
| **Checkbox** | 유전자 선택 |
| **Gene ID** | 유전자 ID (호버 시 Description 툴팁) |
| **Gene Symbol** | 유전자 심볼 (이탤릭체) |
| **Expression Pattern** | TMM 기반 MiniHeatmap |
| **logFC** | 필터/정렬 가능 (빨간색: 양수, 파란색: 음수) |
| **logCPM** | 필터/정렬 가능 |
| **PValue** | 필터/정렬 가능 (과학적 표기법) |
| **FDR** | 필터/정렬 가능 (과학적 표기법) |
| **Regulation** | Upregulated (빨간색) / Downregulated (파란색) / Significant (주황색) |

Search, Analyze, Download, Pagination 기능은 Matrix 탭과 동일합니다. 단, Analyze 메뉴에 Venn Diagram은 포함되지 않습니다.

#### 5. MA Plot 탭

평균 발현량(logCPM, x축) vs 변화량(logFC, y축)을 산점도로 시각화합니다.

**차트 영역**:

| 요소 | 설명 |
|---|---|
| **제목** | "MA Plot: {비교 조건명}" |
| **차트 표시 제한** | Volcano Plot과 동일 (Top 100 ~ All) |
| **통계 요약** | Total genes, Significant (빨간색) 수 표시 |
| **X축** | Average Expression (logCPM) |
| **Y축** | Log Fold Change (logFC) |

**점 색상 구분**:

| 색상 | 조건 |
|---|---|
| **빨간색** | 유의 유전자 (FDR < 0.05). 큰 점, 불투명 |
| **회색** | 비유의 유전자. 작은 점, 반투명 |

**툴팁** (점 호버 시):
- Gene ID, Gene Symbol
- logCPM, logFC, FDR 값
- 유의성 상태 (Significant/Not significant)
- 유의 유전자의 경우 Expression Pattern MiniHeatmap 추가 표시

**Interpretation 패널**: Volcano Plot과 유사한 구조. 차트 해석 가이드와 통계 요약 포함.

**Significant Genes Table**: Volcano Plot 탭과 동일한 구조. Regulation 컬럼에서 logFC > 0이면 Upregulated, logFC < 0이면 Downregulated로 분류.

#### 6. Expression Matrix 탭

P-value와 Fold-change 임계값을 사용자가 직접 설정하여 차등발현 유전자의 발현 매트릭스를 생성하는 탭입니다.

> ℹ️ **참고**: 이 탭에서는 좌측 Comparisons 사이드바가 숨겨집니다. Expression Matrix는 특정 비교 조건이 아닌 워크벤치 전체의 DEG 결과를 통합하여 표시합니다.

**파라미터 입력 영역** (상단 패널):

| 파라미터 | 설명 | 기본값 |
|---|---|---|
| **P-value Cutoff** | 유의성 임계값. 0~1 범위, 0.01 단위 | 0.01 |
| **Fold-change Cutoff (log2)** | 변화량 임계값. 정수 단위 | 2 |
| **Generate Matrix 버튼** | 설정된 파라미터로 발현 매트릭스 생성. 내부적으로 `analyze_diff_expr.pl` 실행 |

- 생성이 완료되면 "Current Matrix: P=0.01, C=2" 형태로 현재 매트릭스 정보 표시
- 새로 생성된 경우 녹색 체크("Newly generated") 표시
- 파라미터 변경 후 Generate Matrix를 클릭하면 검색, 선택, 페이지가 모두 초기화됨

**데이터 테이블**:

| 컬럼 | 설명 |
|---|---|
| **Checkbox** | 유전자 선택. 고정 컬럼 |
| **Gene ID** | 유전자 ID. 고정 컬럼. 호버 시 Description 툴팁 |
| **Gene Symbol** | 유전자 심볼 (이탤릭체). 고정 컬럼 |
| **Expression Pattern** | 샘플별 발현값을 MiniHeatmap으로 시각화 |
| **샘플 컬럼들** | 각 샘플의 log2 centered 발현값 (소수점 2자리) |

- Rows per page: 100 / 500 / 1000 (Matrix 탭보다 적은 옵션)
- logFC/PValue/FDR 개별 필터 기능은 제공되지 않음 (P-value/Fold-change cutoff으로 전체 필터링)

**다운로드**:
- Download 버튼 클릭 시 서버에서 CSV 파일 직접 다운로드 (POST 요청)
- 선택된 유전자가 있으면 해당 유전자만, 없으면 전체 다운로드
- 파일명 예: `diffExpr.P001_C2.selected_50_genes.csv` 또는 `diffExpr.P001_C2.matrix.log2.centered.csv`

**Analyze 드롭다운 메뉴** (Expression Matrix 탭):

| 분석 | 설명 |
|---|---|
| **Heatmap** | 선택된 유전자의 발현량 히트맵 |
| **GO Enrichment** | Gene Ontology 기능 분석 |
| **KEGG Pathway** | KEGG 경로 분석 |
| **Venn Diagram** | 벤 다이어그램 비교 |

#### 7. 공통 인터랙션 패턴

**유전자 선택**:
- 개별 선택: 각 행의 체크박스 클릭
- 전체 선택: 헤더 체크박스로 현재 페이지의 모든 유전자 선택/해제
- 선택 상태는 페이지 변경, 탭 전환, 비교 조건 변경 시 초기화됨
- 선택된 유전자 수는 Analyze 버튼 괄호 안에 실시간 반영

**MiniHeatmap**:
- 각 유전자 행에 표시되는 소형 히트맵
- TMM 정규화 값 기반 색상 표현
- 마우스 호버 시 각 샘플명과 값을 툴팁으로 표시
- 최대 너비 240px (샘플 수에 따라 자동 조절)

**유의성 기준 (기본값)**:
- FDR < 0.05: 유의한 차등 발현
- |logFC| > 1: 2배 이상의 발현 변화 (Volcano Plot 기준)
- Upregulated: logFC > 0 (또는 > 1, 플롯에 따라 다름)
- Downregulated: logFC < 0 (또는 < -1, 플롯에 따라 다름)

<div class="page-break"></div>

### 9. PCA (Principal Component Analysis)

유전자 발현 데이터의 주성분 분석(PCA) 결과를 다양한 시각화로 제공하는 화면입니다. 샘플 간 전반적인 유사성/차이, 복제 샘플의 일관성, 각 주성분에 기여하는 유전자를 탐색할 수 있습니다.

> ⚠️ **주의**: PCA 분석은 **각 그룹에 최소 2개의 biological replicate**가 필요합니다. 조건을 충족하지 못하면 경고 메시지와 함께 현재 샘플 구조(예: "Control (1), Treatment (2)")가 표시되며, 분석 화면에 접근할 수 없습니다.

PCA 화면은 4개의 서브탭으로 구성됩니다:

| 서브탭 | 설명 |
|---|---|
| **PCA Plot** | 주성분 산점도. 샘플 간 전체적 분포 확인 |
| **Sample Correlation** | 전체 샘플 간 상관관계 히트맵 |
| **Replicate Comparison** | 그룹별 복제 샘플 품질 비교 (4개 하위 탭) |
| **Gene Loadings** | 각 주성분에 대한 유전자별 기여도 테이블 |

#### 1. PCA Plot 탭

Plotly.js 기반의 인터랙티브 산점도로 샘플의 주성분 공간 분포를 시각화합니다.

**축 선택** (차트 상단):
- X축 / Y축 각각 드롭다운으로 주성분 선택 (PC1, PC2, ... PCn)
- 기본값: X축 = PC1, Y축 = PC2
- 축 레이블에 분산 설명률 표시 (예: "PC1 (45.23%)")

**차트 구성**:
- 그룹별 12가지 색상 팔레트로 자동 구분
- 마커 크기: 12px, 테두리선 포함
- 차트 크기: 600 x 600px 고정
- Plotly 툴바: 줌, 팬, 스크린샷 저장 등 기본 도구 제공

**Sample Groups 패널** (차트 하단):
- 각 그룹명과 해당 그룹의 샘플 목록 표시
- 그룹별 색상 원형 인디케이터 포함

#### 2. Sample Correlation 탭

전체 샘플 간 상관관계를 클러스터링된 히트맵으로 시각화합니다. 서버에서 scipy를 사용한 계층적 클러스터링 결과(덴드로그램)가 함께 표시됩니다.

**통계 카드** (상단, 4개):

| 카드 | 설명 |
|---|---|
| **Total Samples** | 전체 샘플 수 |
| **Mean Correlation** | 평균 상관계수 |
| **Min Correlation** | 최소 상관계수 |
| **Max Correlation** | 최대 상관계수 (대각선 제외) |

**히트맵 구성**:
- 색상 스케일: Purple (낮은 상관) → White (중간) → Yellow/Gold (높은 상관)
- 행/열 덴드로그램: scipy 계층적 클러스터링 결과 기반
- 그룹 컬러 바: 상단 및 좌측에 각 샘플의 그룹을 색상으로 표시
- 마우스 호버 시 두 샘플명과 상관계수 값 표시
- 차트 크기: 샘플 수에 따라 동적 조절 (최소 600px, 샘플당 +80px)

**Interpretation Guide 패널** (차트 하단):

| 상관계수 범위 | 해석 |
|---|---|
| **≥ 0.95** | 매우 높은 상관. 우수한 복제 품질 |
| **0.85 - 0.95** | 높은 상관. 양호한 복제 품질 |
| **0.70 - 0.85** | 중간 상관. 기술적 변이 확인 필요 |
| **< 0.70** | 낮은 상관. 잠재적 문제 또는 큰 생물학적 차이 |

#### 3. Replicate Comparison 탭

선택한 그룹 내 복제 샘플 간 일관성을 다양한 방법으로 비교하는 탭입니다. 좌측에 그룹 선택 사이드바가 있고, 우측 영역에 4개의 하위 탭이 있습니다.

**좌측 사이드바** (w-64):
- "Select Sample Group" 레이블
- 그룹 목록 버튼 (클릭으로 그룹 전환)
- 선택된 그룹은 파란색 강조

##### 3-1. Fragment Count 하위 탭

선택한 그룹의 복제 샘플별 프래그먼트(시퀀싱 리드) 수를 막대 차트로 표시합니다.

**통계 카드** (상단, 4개):

| 카드 | 설명 |
|---|---|
| **Total Fragments** | 해당 그룹 전체 프래그먼트 합계 |
| **Mean per Sample** | 샘플당 평균 프래그먼트 수 |
| **Min Fragments** | 최소 프래그먼트 수 |
| **Max Fragments** | 최대 프래그먼트 수 |

**차트**: Plotly 막대 차트 (700 x 450px). X축: 샘플명, Y축: Fragment Count.

> ℹ️ **참고**: 복제 샘플 간 프래그먼트 수가 크게 차이나면 라이브러리 준비 과정의 기술적 문제를 의심할 수 있습니다.

##### 3-2. Scatter Plot 하위 탭

복제 샘플 간 유전자 발현량을 쌍별(pairwise) 산점도 매트릭스로 비교합니다.

**차트 구성**:
- N x N 서브플롯 매트릭스 (N = 복제 샘플 수)
- 대각선 위치: 샘플명 텍스트 표시
- 비대각선 위치: 두 샘플 간 발현량 산점도
- 대칭 축 범위 적용 (모든 서브플롯 동일 스케일)
- 차트 크기: 500 x 500px
- 최대 1,000개 유전자 표시

> 💡 **해석**: 대각선 직선에 점들이 밀집되어 있을수록 복제 샘플 간 발현 패턴이 일치합니다. 대각선에서 벗어난 점은 차등 발현 유전자이거나 기술적 변이를 나타냅니다.

##### 3-3. MA Plot 하위 탭

복제 샘플 간 발현량 차이를 MA plot 매트릭스로 시각화합니다.

**차트 구성**:
- N x N 서브플롯 매트릭스
- X축 (A): 두 복제의 평균 log2 발현값
- Y축 (M): 두 복제 간 log2 fold change (차이)
- 대각선 위치: 샘플명 텍스트 표시
- M=0 기준선 표시 (회색 점선)
- 대칭 축 범위 적용
- 차트 크기: 500 x 500px
- 최대 1,000개 유전자 표시

> 💡 **해석**: 점들이 M=0 주변에 집중되어 있으면 복제 간 발현이 일관적입니다. M=0에서 크게 벗어난 점은 복제 간 발현 차이가 큰 유전자입니다.

##### 3-4. Correlation Heatmap 하위 탭

선택한 그룹의 복제 샘플 간 상관관계를 히트맵으로 표시합니다.

**통계 카드** (상단, 3개):

| 카드 | 설명 |
|---|---|
| **Mean Correlation** | 복제 간 평균 상관계수 |
| **Min Correlation** | 최소 상관계수 |
| **Max Correlation** | 최대 상관계수 |

**히트맵 구성**:
- 색상 스케일: Cyan (낮은 상관) → Light Gray (중간) → Magenta (높은 상관)
- 차트 크기: 500 x 400px
- 마우스 호버 시 두 샘플명과 상관계수(소수점 3자리) 표시

> ℹ️ **참고**: 대각선은 항상 1.0 (자기 자신과의 상관). 상관계수 ≥ 0.9이면 양호한 복제 일관성, < 0.7이면 기술적 문제 또는 생물학적 변이를 의심합니다.

#### 4. Gene Loadings 탭

각 유전자가 주성분(PC)에 기여하는 정도(로딩 값)를 테이블로 제공합니다. 특정 주성분을 구동하는 핵심 유전자를 식별하는 데 활용합니다.

**컨트롤 패널** (상단):

| 컨트롤 | 설명 | 기본값/옵션 |
|---|---|---|
| **Sort by PC** | 정렬 기준 주성분 선택 | PC1 (드롭다운으로 PC1~PCn 선택) |
| **Sort order** | 정렬 순서 | Highest absolute value / Lowest absolute value |
| **Genes per page** | 페이지당 유전자 수 | 25 / 50 / 100 / 200 |
| **Total genes** | 전체 유전자 수 표시 (우측) | - |

**데이터 테이블**:

| 컬럼 | 설명 |
|---|---|
| **Gene ID** | 유전자 ID. 좌측 고정(sticky) 컬럼 |
| **PC1 ~ PC5** | 각 주성분별 로딩 값 (소수점 6자리). 헤더 클릭으로 정렬 전환 |
| **Abs(PCn)** | 현재 정렬 기준 PC의 절대값. 파란색 강조 |

- 정렬 기준 PC 컬럼은 굵은 글씨로 강조
- PC 헤더 클릭 시: 같은 PC면 정렬 순서 토글, 다른 PC면 해당 PC 기준 내림차순으로 전환
- 서버 사이드 정렬 및 페이지네이션 적용 (API 호출)

**페이지네이션** (하단):
- "Showing page X of Y (시작-끝 of 전체)" 형태의 위치 정보
- First / Previous / Next / Last 버튼

<div class="page-break"></div>

### 10. Clustering Analysis

차등발현 유전자의 발현 패턴을 기반으로 클러스터링 분석을 수행하는 화면입니다. 세 가지 클러스터링 방법을 제공하며, 상단 탭으로 전환합니다.

| 클러스터링 방법 | 설명 |
|---|---|
| **Hierarchical Tree Clustering** | DEG 기반 계층적 클러스터링. 덴드로그램 트리 절단 |
| **Mfuzz** | Fuzzy c-means 기반 시계열 발현 패턴 클러스터링 |
| **WGCNA** | 가중 유전자 공발현 네트워크 분석. 모듈 탐지 |

세 방법 모두 동일한 **3단 레이아웃** 구조를 공유합니다:
- **좌측**: 파라미터 패널 (접기/펼치기 가능, w-80 ↔ w-16)
- **중앙**: 클러스터/모듈 목록 사이드바 (w-64)
- **우측**: 선택된 클러스터/모듈의 상세 정보 (발현 패턴 차트 + 유전자 테이블)

> ℹ️ **참고**: 모든 클러스터링 방법은 처음 접근 시 기본 파라미터로 자동 실행됩니다. 기존 결과가 있으면 해당 결과를 로드합니다. 분석 실행 중에는 전체 화면 로딩 오버레이가 표시됩니다.

#### 1. Hierarchical Tree Clustering

DEG 분석 결과를 기반으로 계층적 클러스터링을 수행하고, 트리를 특정 높이에서 절단하여 서브클러스터를 생성합니다.

**파라미터 패널**:

| 파라미터 | 설명 | 기본값 |
|---|---|---|
| **P-value** | DEG 유의성 임계값 | 0.05 |
| **Fold Change** | Log2 fold change 임계값 | 2 |
| **Ptree** | 트리 절단 높이 백분위 (1-100). 값이 클수록 큰 클러스터, 작을수록 세분화 | 30 |
| **Run Clustering** | 설정된 파라미터로 클러스터링 실행 버튼 | - |

**클러스터 사이드바**:
- "Clusters (N)" 헤더에 전체 클러스터 수 표시
- 클러스터 ID 오름차순 정렬 (Cluster 1, 2, 3...)
- 각 항목에 클러스터명과 유전자 수 표시
- 선택된 클러스터는 파란색 강조

**클러스터 상세 - 발현 패턴 차트**:
- Recharts LineChart (높이 500px, 반응형 너비)
- X축: 샘플명, Y축: log2(Expression)
- 차트 헤더에 유전자 수, P-value, Log2 FC, Ptree 파라미터 정보 표시

**차트 토글 스위치** (우측 상단, 3개):

| 토글 | 설명 | 기본 상태 |
|---|---|---|
| **Genes** | 개별 유전자 발현 라인 표시 (회색 반투명, 최대 300개) | OFF |
| **Mean** | 평균 발현 라인 (파란색 실선, 굵기 3px) | ON |
| **Median** | 중앙값 발현 라인 (초록색 점선, 굵기 3px) | ON |

- 툴팁: 호버 시 샘플명, Mean, Median 값 표시
- 토글 상태는 클러스터 전환 시에도 유지됨

**클러스터 상세 - 유전자 테이블**:

| 컬럼 | 설명 |
|---|---|
| **Checkbox** | 유전자 선택 |
| **Gene ID** | 유전자 ID |
| **Gene Symbol** | 유전자 심볼 |
| **Expression Pattern** | MiniHeatmap으로 발현 패턴 시각화 |
| **샘플 컬럼들** | 각 샘플의 발현값 |

- 검색: 유전자 ID/심볼 검색 (서버 사이드)
- 정렬: Gene ID 기준
- Rows per page: 100 / 500 / 1,000 / 2,000 / 3,000
- 서버 사이드 페이지네이션 적용

**Analyze 드롭다운 메뉴**:

| 분석 | 설명 |
|---|---|
| **Heatmap** | 선택된 유전자의 발현량 히트맵 |
| **GO Enrichment** | Gene Ontology 기능 분석 |
| **KEGG Pathway** | KEGG 경로 분석 |
| **Venn Diagram** | 벤 다이어그램 (DEG 탭으로 이동) |

**다운로드**: TSV 형식. 선택된 유전자 또는 전체 클러스터 유전자 다운로드.

#### 2. Mfuzz

Fuzzy c-means 알고리즘을 사용한 시계열 발현 패턴 클러스터링입니다. 각 유전자는 membership 값(0~1)으로 클러스터에 대한 소속 정도가 표현됩니다.

**파라미터 패널 - Input Source Type** (라디오 버튼):

| 소스 타입 | 설명 | 권장 |
|---|---|---|
| **DEG-filtered** | P-value/Fold Change로 필터링된 DEG 사용 (~2,000 유전자) | - |
| **Variance-filtered** | MAD 기반 상위 N개 고변동 유전자 선택. 패턴 탐색에 최적 | Recommended |
| **Full TMM** | 전체 TMM 정규화 매트릭스 사용. 노이즈 유입 가능 | Not Recommended |

**소스 타입별 추가 파라미터**:

| 파라미터 | 소스 타입 | 설명 | 기본값 |
|---|---|---|---|
| **P-value** | DEG-filtered | 유의성 임계값 | 0.05 |
| **Fold Change** | DEG-filtered | Log2 fold change 임계값 | 2 |
| **Top N Genes** | Variance-filtered | 고변동 유전자 수 (3,000~10,000 권장) | 8,000 |

**클러스터링 파라미터**:

| 파라미터 | 설명 | 기본값 |
|---|---|---|
| **Cluster Count** | 클러스터 수 (c). 범위: 2~20 | 16 |
| **M value** | Fuzzifier 파라미터. 빈칸이면 자동 추정 | auto |
| **Min Membership** | 최소 소속 임계값 (0~1). 이 값 미만의 유전자는 제외 | 0.5 |
| **Run Clustering** | 클러스터링 실행 버튼 | - |

**클러스터 사이드바**: Tree와 동일 구조. 클러스터 ID 오름차순 정렬.

**클러스터 상세 - 발현 패턴 차트**: Tree와 동일한 토글 스위치(Genes/Mean/Median) 구조.
- 차트 헤더에 Source, P-value/Top genes, Clusters, Min membership 파라미터 정보 표시
- Genes 토글 시 membership 기준 상위 300개 유전자만 표시

**클러스터 상세 - 유전자 테이블**: Tree와 동일 구조에 **Membership** 컬럼 추가.
- Membership: 해당 클러스터에 대한 소속 정도 (0~1, 높을수록 대표적)

#### 3. WGCNA

Weighted Gene Co-expression Network Analysis. 유전자 공발현 네트워크를 구축하고 유사한 발현 패턴을 보이는 유전자 모듈을 탐지합니다.

**파라미터 패널 - Input Source Type**: Mfuzz와 동일한 3가지 소스 타입 (DEG-filtered / Variance-filtered / Full TMM).
- Variance-filtered 기본 Top N Genes: 5,000 (Mfuzz의 8,000보다 작음, 3,000~5,000 권장)

**WGCNA 고유 파라미터**:

| 파라미터 | 설명 | 기본값 |
|---|---|---|
| **Soft Thresholding Power** | 네트워크 연결 가중치 조절. Auto-detect 또는 수동 입력 (1~30) | Auto-detect |
| **Run WGCNA Analysis** | 분석 실행 버튼 | - |

**Advanced Parameters** (접기/펼치기):

| 파라미터 | 설명 | 기본값 |
|---|---|---|
| **Min Module Size** | 모듈당 최소 유전자 수 (10~200) | 30 |
| **Deep Split** | 클러스터 분할 민감도 (0~4). 클수록 세분화 | 2 |
| **Merge Cut Height** | 유사 모듈 병합 임계값 (0~1). 작을수록 적극적으로 병합 | 0.25 |

**모듈 사이드바** (WGCNA 고유):
- "Modules (N)" 헤더
- 유전자 수 내림차순 정렬 (가장 큰 모듈부터)
- 각 모듈명은 WGCNA 표준 색상명 (turquoise, blue, brown 등)
- 모듈 색상 인디케이터 (8x8 컬러 박스) 표시
- **유전자 검색**: 검색창에 Gene ID 입력 후 검색 → 해당 유전자가 포함된 모듈만 필터링
- 검색 결과 상태 표시 ("Showing modules with: [검색어]")
- X 버튼으로 검색 초기화

**모듈 상세 - Module Eigengene Pattern 차트**:
- Recharts LineChart (높이 400px, 반응형 너비)
- Module Eigengene 라인: 모듈 대표 색상으로 굵은 실선 (3px)
- 차트 헤더에 모듈 색상 인디케이터, 유전자 수, 파라미터 정보 표시
- Show Genes 토글: ON 시 kME 기준 상위 100개 유전자의 개별 라인 표시 (회색 반투명)

> ℹ️ **참고**: Tree/Mfuzz의 Mean/Median 통계 대신, WGCNA는 Module Eigengene(모듈의 제1 주성분)을 중심 경향으로 사용합니다.

**모듈 상세 - 유전자 테이블**: 기본 구조는 Tree와 동일하며, WGCNA 고유 컬럼이 추가됩니다.

| 추가 컬럼 | 설명 |
|---|---|
| **Module Membership (kME)** | 모듈 Eigengene과의 상관계수. 높을수록 모듈의 핵심 유전자 |

#### 4. 공통 인터랙션 패턴 (전체 클러스터링 방법)

**파라미터 패널 접기/펼치기**:
- 펼침 상태: w-80 (320px). 파라미터 입력 및 Run 버튼 표시
- 접힌 상태: w-16 (64px). 세로 "Params" 텍스트와 화살표 아이콘만 표시
- 우측 얇은 세로 버튼(w-8)으로 접기 전환
- 접힌 상태에서 클릭하면 펼쳐짐

**유전자 선택 및 분석**:
- 유전자 테이블에서 체크박스로 선택
- 선택 상태는 클러스터/모듈 전환 시 초기화
- Analyze 메뉴: Heatmap, GO Enrichment, KEGG Pathway, Venn Diagram
- 다운로드: TSV 형식

**파라미터 변경 시 동작**:
- 파라미터 변경 → 기존 결과 자동 조회 (캐싱된 결과가 있으면 즉시 표시)
- Run 버튼 클릭 → 새로운 분석 실행 (전체 화면 로딩 오버레이)
- 데이터셋 크기에 따라 분석에 수 분이 소요될 수 있음

<div class="page-break"></div>

### 11. Heatmap

유전자 발현량을 색상 매트릭스로 시각화하는 화면입니다. 사용자 정의 유전자 세트를 관리하고, 다양한 정규화 방법과 클러스터링 옵션으로 히트맵을 생성할 수 있습니다.

#### 화면 구성

| 영역 | 위치 | 설명 |
|---|---|---|
| **Interesting Gene Sets 사이드바** | 좌측 (280px, 가로 리사이즈 가능) | 유전자 세트 트리 관리 |
| **히트맵 컨트롤** | 우측 상단 | 정규화/클러스터링 옵션 |
| **히트맵 시각화** | 우측 메인 | Plotly.js 기반 히트맵 |

---

#### Interesting Gene Sets 사이드바

유전자 세트를 폴더/파일 트리 구조로 관리하는 사이드바입니다.

**헤더**:
- "Interesting Gene Sets" 타이틀
- **+ 버튼**: 새 유전자 세트 생성 모달 열기

**검색**:
- 검색창에 텍스트 입력 시 파일명 기준 실시간 필터링
- 일치하는 항목의 상위 폴더가 자동 펼쳐짐
- 검색어와 일치하는 부분이 노란색으로 하이라이트
- X 버튼으로 검색 초기화

**트리 구조**:
- **폴더** (노란 폴더 아이콘): 클릭으로 펼침/접기. 최상위 폴더는 마운트 시 자동 펼침
- **파일** (문서 아이콘): 유전자 세트 파일 (.txt)

**파일 선택**:
- 단일 클릭: 해당 파일 하나만 선택 → 히트맵에 해당 유전자 표시
- **Ctrl+Click**: 다중 선택 토글. 여러 파일의 유전자를 합쳐서 히트맵에 표시 (중복 제거)
- 선택된 파일은 파란색 배경으로 강조
- 사이드바 하단에 "Ctrl+Click to select multiple" 안내 텍스트

**마우스 호버 액션**:

| 대상 | 호버 시 표시 버튼 | 동작 |
|---|---|---|
| **파일** | 연필 아이콘 (Edit) | 유전자 세트 편집 모달 열기 |
| **파일** | 휴지통 아이콘 (Delete) | 삭제 확인 후 삭제 |
| **폴더** | 휴지통 아이콘 (Delete) | 폴더 삭제 확인 후 삭제 |

> ⚠️ **주의**: 폴더 삭제 시 하위 파일이 모두 삭제됩니다.

---

#### Gene Set Editor 모달

유전자 세트를 생성하거나 편집하는 모달입니다. + 버튼 또는 파일 편집 아이콘으로 열립니다.

**모달 상단 - 저장 위치 선택**:
- 폴더 트리에서 저장 위치 선택 (클릭으로 선택, 배경색 강조)
- **New Folder** 버튼: 선택된 폴더 하위에 새 폴더 생성
  - 인라인 입력 필드 표시 → 폴더명 입력 → Enter로 확정, Escape로 취소
- 마지막으로 선택한 폴더가 localStorage에 저장되어 다음 생성 시 자동 선택

##### 생성 모드 (Create)

두 가지 입력 탭이 제공됩니다:

**탭 1 - Text Input** (수동 입력):

| 필드 | 설명 |
|---|---|
| **File Name** | 유전자 세트 파일명 (.txt 자동 추가) |
| **Gene IDs** | 텍스트 영역에 유전자 ID를 한 줄에 하나씩 입력 |

- **Create** 버튼: 입력된 유전자로 새 파일 생성

**탭 2 - Upload Files** (파일 업로드):

| 버튼 | 설명 |
|---|---|
| **Choose Files** | .txt 파일 개별 선택 (복수 선택 가능) |
| **Choose Folder** | 폴더 통째로 선택 → 하위 .txt 파일 자동 인식 |

- 선택된 파일 목록이 트리 형태로 미리보기 표시 (파일명 + 유전자 수)
- **Upload** 버튼: 선택된 파일들을 지정 폴더에 업로드

##### 편집 모드 (Edit)

- 기존 파일의 유전자 목록이 텍스트 영역에 로드됨
- 파일명은 읽기 전용으로 표시
- 유전자 ID를 추가/삭제 후 **Save** 버튼으로 저장

##### 폴더 관리

모달 내에서도 폴더 삭제가 가능합니다:
- 폴더에 마우스 호버 시 휴지통 아이콘 표시
- 클릭 시 삭제 확인 후 해당 폴더와 하위 파일 삭제

---

#### 히트맵 컨트롤

유전자 세트를 선택하면 히트맵 상단에 정규화 및 클러스터링 옵션이 표시됩니다.

**Normalization** (드롭다운, 3가지 방법):

| 방법 | 설명 |
|---|---|
| **Z-score** | 유전자별 평균=0, 표준편차=1로 스케일링. 유전자 간 상대적 패턴 비교에 적합 |
| **Log2 Centered** | log2 변환 후 유전자별 평균을 빼서 센터링 |
| **Log2FC vs Reference** | 선택된 기준 샘플 대비 log2 fold change 계산 |

**Reference Sample** (드롭다운):
- Log2FC vs Reference 선택 시에만 표시됨
- 기준이 될 샘플을 선택

**Clustering** (드롭다운, 3가지 방법):

| 방법 | 설명 |
|---|---|
| **Ward** | Ward의 최소 분산 기준. 유사한 크기의 클러스터 생성 경향 |
| **Average** | 평균 연결법 (UPGMA). 균형 잡힌 클러스터링 |
| **Complete** | 최대 연결법. 조밀한 클러스터 생성 경향 |

- 선택된 클러스터링 방법에 따라 히트맵의 유전자(행) 순서가 재배열됨

---

#### 히트맵 시각화

Plotly.js 기반의 인터랙티브 히트맵입니다.

**타이틀**:
- 선택된 유전자 세트 파일명 표시 (복수 선택 시 모두 나열)
- 유전자 수 및 적용된 정규화 방법 표시

**색상 스케일**:
- 사용자 설정(Settings)에서 지정한 컬러스케일 적용
- Z-score 모드: 중앙값(zmid)=0, 범위는 데이터의 99th 백분위수 절대값 기준 자동 클리핑 (최소 2, 최대 5)
- 히트맵 우측에 컬러바 표시

**동적 크기 조절**:
- 높이: 유전자 수에 따라 자동 조절 (최소 300px ~ 최대 1,200px, 유전자당 2~15px)
- 너비: 컨테이너에 반응형 적용

**인터랙션**:

| 동작 | 설명 |
|---|---|
| **드래그** | 특정 영역 확대 (줌) |
| **더블 클릭** | 줌 초기화 (전체 보기로 복원) |
| **호버** | 유전자명, 샘플명, 발현값 툴팁 표시 |
| **샘플 클릭** (Log2FC 모드) | 클릭한 샘플을 새 기준 샘플(Reference)로 변경 |

**유전자가 많을 때 - 확대(줌) 활용**:

유전자 수가 많으면 Y축 레이블이 겹쳐 유전자명을 읽기 어렵습니다. 이때 확대 기능을 사용하면 특정 구간의 유전자명을 선명하게 확인할 수 있습니다.

- 히트맵 위에서 **마우스를 드래그**하면 해당 영역이 확대됩니다
- **더블 클릭**하면 전체 보기로 되돌아갑니다
- 확대 시 보이는 유전자 수가 줄어들수록 Y축 폰트가 자동으로 커집니다

| 확대 후 표시 유전자 수 | Y축 폰트 크기 |
|---|---|
| ≤10개 | 14px |
| ≤20개 | 12px |
| ≤50개 | 10px |
| ≤100개 | 8px |
| >100개 | 6px |

**이미지 다운로드**:
- Plotly 툴바의 카메라 아이콘 클릭 → 고해상도 PNG 다운로드 (10배 스케일)
- 히트맵 하단 안내: "Drag to zoom, double-click to reset | Use camera icon in toolbar to download high-resolution PNG"

**캐싱**:
- 동일한 유전자 세트 + 정규화 + 클러스터링 조합의 결과가 메모리에 캐싱됨
- 옵션 변경 후 이전 설정으로 돌아가면 API 호출 없이 즉시 표시

---

#### Heatmap Analysis 모달

DEG 탭이나 Clustering 탭의 **Analyze → Heatmap** 메뉴에서 열리는 모달 형태의 히트맵입니다.

| 항목 | 설명 |
|---|---|
| **타이틀** | "Expression Heatmap - {비교군명}" |
| **너비** | 900px 고정 |
| **컨트롤** | Normalization, Reference Sample, Clustering — 본 화면과 동일 |
| **인터랙션** | 줌, 호버, 기준 샘플 변경, 폰트 자동 조절 — 본 화면과 동일 |
| **닫기** | 하단 Close 버튼 또는 모달 외부 클릭 |

> ℹ️ **참고**: 이 모달은 Interesting Gene Sets가 아닌, 해당 분석에서 선택된 유전자 목록으로 히트맵을 생성합니다.

<div class="page-break"></div>

### 12. Venn Diagram

최대 3개의 유전자 세트 간 교집합/차집합을 시각적으로 비교하는 화면입니다. 벤 다이어그램의 각 영역을 클릭하여 해당 유전자의 발현 매트릭스를 조회하고, GO/KEGG/Heatmap 분석을 수행할 수 있습니다.

#### 화면 구성

| 영역 | 위치 | 설명 |
|---|---|---|
| **Gene Sets 입력 패널** | 좌측 (224px, 접기 가능) | 유전자 세트 입력/관리 |
| **벤 다이어그램** | 중앙 (500x500px) | Highcharts 기반 벤 다이어그램 |
| **유전자 결과 테이블** | 우측 (나머지 영역) | 선택 영역의 발현 매트릭스 |

---

#### Gene Sets 입력 패널

유전자 세트를 입력하고 관리하는 접이식 좌측 패널입니다.

**패널 구성 요소** (세트당):

| 요소 | 설명 |
|---|---|
| **세트 이름** | 텍스트 입력으로 편집 가능 (기본: A, B, C) |
| **clear 버튼** | 유전자만 삭제 (세트 유지) |
| **delete 버튼** | 세트 전체 삭제 |
| **텍스트 영역** | 유전자 ID 입력 (높이 192px). 줄바꿈, 쉼표, 세미콜론으로 구분 |
| **유전자 수 표시** | 입력된 유전자 수 실시간 표시 |

**패널 하단 버튼**:
- **+ Add Set**: 새 세트 추가 (최대 3개까지)
- **Reset All Sets**: 모든 세트 초기화 (빨간색 버튼)

**접기/펼치기**:
- 우측 가장자리 버튼으로 접기 전환
- 접힌 상태: 세로 "Gene Sets" 텍스트와 펼침 아이콘만 표시

> ℹ️ **참고**: 유전자 세트 데이터는 상위 컴포넌트(WorkbenchDetail)에서 관리되므로, 다른 탭으로 이동 후 돌아와도 입력 내용이 유지됩니다. DEG/Clustering 탭의 **Analyze → Venn Diagram** 메뉴를 통해 다른 탭에서 유전자를 전달받을 수도 있습니다.

---

#### 벤 다이어그램

Highcharts Venn 모듈 기반의 인터랙티브 다이어그램입니다.

**표시 조건**:
- 최소 2개의 유전자 세트가 필요
- 각 세트에 1개 이상의 유전자가 있어야 함
- 조건 미충족 시 안내 메시지 표시

**2-세트 다이어그램** (A, B):

| 영역 | 설명 |
|---|---|
| **A Only** | A에만 존재하는 유전자 |
| **B Only** | B에만 존재하는 유전자 |
| **A ∩ B** | A와 B의 교집합 |

**3-세트 다이어그램** (A, B, C):

| 영역 | 설명 |
|---|---|
| **A Only** | A에만 존재하는 유전자 |
| **B Only** | B에만 존재하는 유전자 |
| **C Only** | C에만 존재하는 유전자 |
| **A ∩ B** | A, B 교집합 (C 제외) |
| **B ∩ C** | B, C 교집합 (A 제외) |
| **A ∩ C** | A, C 교집합 (B 제외) |
| **A ∩ B ∩ C** | 3개 세트 모두의 교집합 |

**영역 클릭 인터랙션**:
1. 다이어그램의 원 또는 겹침 영역 클릭
2. 마우스 위치에 컨텍스트 메뉴 표시:
   - **○ Exclusive**: 해당 영역에만 속하는 유전자 (다른 세트에 없는 유전자)
   - **● Total**: 해당 세트에 포함된 전체 유전자 (다른 세트와 겹치는 유전자 포함)
   - 각 옵션 옆에 유전자 수 표시
3. 옵션 선택 → 우측 테이블에 해당 유전자의 발현 데이터 로드

- **Ctrl+Click**: 기존 선택에 새 유전자를 추가 (누적 선택)

**호버 툴팁**: 해당 영역의 Exclusive/Total 유전자 수 표시

**다이어그램 다운로드**: 다이어그램 상단 또는 Highcharts 메뉴에서 PNG, JPEG, PDF, SVG 형식으로 다운로드

---

#### 유전자 결과 테이블

벤 다이어그램 영역 선택 후 표시되는 발현 매트릭스 테이블입니다.

**테이블 상단 툴바**:

| 요소 | 설명 |
|---|---|
| **Matrix Type** | Raw / TPM / TMM 전환 버튼. 선택 시 서버에서 해당 매트릭스 재조회 |
| **Download** | 선택된 유전자의 발현 데이터를 CSV로 다운로드 (초록색 버튼) |
| **Analyze** | 드롭다운 메뉴 (Heatmap / GO Enrichment / KEGG Pathway) |

**Matrix Type 설명**:

| 타입 | 설명 |
|---|---|
| **Raw** | 원시 리드 카운트 |
| **TPM** | Transcripts Per Million. 샘플 간 비교에 적합 |
| **TMM** | Trimmed Mean of M-values. 정규화된 발현량 |

**테이블 컬럼**:

| 컬럼 | 설명 | 고정 여부 |
|---|---|---|
| **체크박스** | 유전자 선택 (헤더 체크박스로 현재 페이지 전체 선택) | 좌측 고정 |
| **#** | 행 번호 | 좌측 고정 |
| **Gene ID** | 유전자 ID (호버 시 Gene Description 툴팁) | 좌측 고정 |
| **Gene Symbol** | 유전자 심볼 (Gene ID와 다를 경우 이탤릭) | 좌측 고정 |
| **Expression Pattern** | MiniHeatmap으로 발현 패턴 시각화 (샘플당 16px, 최대 240px) | - |
| **샘플 컬럼들** | 각 샘플의 발현값 | - |

- 좌측 4개 컬럼(체크박스, #, Gene ID, Gene Symbol)은 가로 스크롤 시에도 고정
- 헤더는 세로 스크롤 시에도 고정

**페이지네이션**:
- 테이블 상단과 하단 모두에 표시
- Rows per page: 100 / 500 / 1,000 / 2,000 / 5,000
- 현재 범위 표시 (예: "1-500 of 2,543")
- 페이지 번호 버튼 (긴 목록은 말줄임 처리) + Previous/Next 버튼

**빈 상태**:
- 영역 미선택: "Click on the Venn diagram to view genes" 안내 메시지

---

#### Analyze 드롭다운 메뉴

유전자를 선택(체크박스)한 후 사용할 수 있는 분석 기능입니다.

| 분석 | 설명 |
|---|---|
| **Heatmap** | 선택된 유전자의 발현량 히트맵 모달 표시 |
| **GO Enrichment** | Gene Ontology 기능 분석 (BP, MF, CC 카테고리) |
| **KEGG Pathway** | KEGG 경로 분석 |

> ℹ️ **참고**: 분석 수행을 위해서는 테이블에서 유전자를 먼저 선택해야 합니다.
