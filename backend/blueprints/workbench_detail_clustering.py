"""
Clustering Analysis API
클러스터링 분석 (Tree Cutting, Mfuzz, WGCNA) 결과 조회 및 실행 API
"""

import os
import glob
import subprocess
import pandas as pd
import numpy as np
from scipy.cluster import hierarchy
from scipy.spatial.distance import squareform
from flask import Blueprint, jsonify, request, send_file
from backend.utils import database
from backend.blueprints.workbench_utils import get_workbench_schema, load_gene_annotations
from backend.utils.logger import setup_module_logger
from config.shared_config import SharedConfig

logger = setup_module_logger(__name__, 'INFO')

clustering_bp = Blueprint('clustering', __name__, url_prefix='/api/workbenches')


def run_tree_clustering_docker(workbench_id: int, p_value: float, fold_change: float, ptree: int):
    """
    define_clusters_by_cutting_tree.pl Docker 실행

    Args:
        workbench_id: 워크벤치 ID
        p_value: P-value cutoff
        fold_change: Fold change cutoff
        ptree: Ptree parameter

    Returns:
        dict: {
            "success": bool,
            "clusters": list,
            "total": int,
            "output_dir": str,
            "error": str (실패 시)
        }
    """
    try:
        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return {
                "success": False,
                "error": "Workbench not found"
            }

        # 경로 설정
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        workbench_dir = workbench_schema['base']
        deg_dir = workbench_schema['deg']

        matrix_name = f"diffExpr.P{p_value}_C{fold_change}.matrix.RData"
        matrix_path = os.path.join(deg_dir, 'edgeR', matrix_name)

        # Matrix 파일 존재 확인 및 자동 생성
        if not os.path.exists(matrix_path):
            logger.info(f"📁 [CLUSTERING] DEG matrix not found, generating: {matrix_name}")

            # run_dea() 호출하여 파일 생성
            from backend.pipeline.utils.de_analysis import run_dea

            # TMM matrix 경로
            counts_dir = workbench_schema['quanti']['counts']
            tmm_matrix_file = os.path.join(counts_dir, 'genes.TMM.matrix')

            # samples.txt 경로
            samples_dir = workbench_schema['quanti']['samples']
            samples_file = os.path.join(samples_dir, 'samples.txt')

            # 파일 존재 확인
            if not os.path.exists(tmm_matrix_file):
                logger.error(f"❌ [CLUSTERING] TMM matrix not found: {tmm_matrix_file}")
                return {
                    "success": False,
                    "error": "TMM matrix file not found. Please run quantification first."
                }

            if not os.path.exists(samples_file):
                logger.error(f"❌ [CLUSTERING] Samples file not found: {samples_file}")
                return {
                    "success": False,
                    "error": "Samples file not found. Please run quantification first."
                }

            # run_dea() 호출
            edger_dir = os.path.join(deg_dir, 'edgeR')
            workbench_root = workbench_schema["base"]
            dea_result = run_dea(
                workbench_root=workbench_root,
                output_dir=edger_dir,
                tmm_matrix_file=tmm_matrix_file,
                samples_file=samples_file,
                workbench_id=workbench_id,
                worker_id="clustering_worker",
                p_value=p_value,
                fold_change=fold_change
            )

            if not dea_result.get('success', False):
                error_msg = dea_result.get('error', 'Unknown error')
                logger.error(f"❌ [CLUSTERING] Failed to generate DEG matrix: {error_msg}")
                return {
                    "success": False,
                    "error": f"Failed to generate DEG matrix: {error_msg}"
                }

            logger.info(f"✅ [CLUSTERING] DEG matrix generated successfully: {matrix_name}")
        else:
            logger.info(f"✅ [CLUSTERING] Using existing DEG matrix: {matrix_name}")

        # 호스트 경로로 변환 (VizR 컨테이너 경로 → 호스트 경로)
        host_workbench_dir = workbench_dir.replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)
        logger.info(f"🔄 [CLUSTERING] Path conversion: container→host")
        logger.info(f"   ├─ Container: {workbench_dir}")
        logger.info(f"   └─ Host: {host_workbench_dir}")

        # Docker 명령어 구성
        clustering_command = (
            f"/usr/local/bin/Analysis/DifferentialExpression/define_clusters_by_cutting_tree.pl "
            f"-R {matrix_name} "
            f"--Ptree {ptree}"
        )

        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_workbench_dir}:/data",
            "-w", "/data/deg/edgeR",  # 작업 디렉토리 설정
            SharedConfig.TRINITY_IMAGE,
            "bash", "-c",
            clustering_command
        ]

        logger.info(f"🔍 [CLUSTERING][DEBUG] clustering_command: {clustering_command}")

        # 실행
        logger.info(f"🚀 [CLUSTERING] Running tree clustering:")
        logger.info(f"├─ Workbench: {workbench['name']} (ID: {workbench_id})")
        logger.info(f"├─ P-value: {p_value}")
        logger.info(f"├─ Fold Change: {fold_change}")
        logger.info(f"├─ Ptree: {ptree}")
        logger.info(f"└─ Command: {' '.join(docker_cmd)}")

        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10분 타임아웃
        )

        if result.returncode != 0:
            logger.error(f"❌ [CLUSTERING] Docker execution failed:")
            logger.error(f"   └─ stderr: {result.stderr}")
            return {
                "success": False,
                "error": f"Clustering failed: {result.stderr}"
            }

        logger.info(f"✅ [CLUSTERING] Docker execution completed")

        # 결과 수집
        output_dir = os.path.join(deg_dir, 'edgeR', f"{matrix_name}.clusters_fixed_P_{ptree}")

        if not os.path.exists(output_dir):
            logger.error(f"❌ [CLUSTERING] Output directory not created: {output_dir}")
            return {
                "success": False,
                "error": "Clustering output directory not found"
            }

        matrix_files = sorted(glob.glob(os.path.join(output_dir, "subcluster_*.matrix")))

        if not matrix_files:
            logger.warning(f"⚠️ [CLUSTERING] No cluster files generated")
            return {
                "success": False,
                "error": "No cluster files generated"
            }

        # 클러스터 메타데이터 생성
        clusters = []
        for file_path in matrix_files:
            filename = os.path.basename(file_path)
            cluster_id = filename.replace("_log2_medianCentered_fpkm.matrix", "")

            # 유전자 수 계산 (헤더 제외)
            with open(file_path, 'r', encoding='utf-8') as f:
                gene_count = sum(1 for line in f) - 1

            clusters.append({
                "id": cluster_id,
                "gene_count": gene_count,
                "file_name": filename
            })

        logger.info(f"✅ [CLUSTERING] Generated {len(clusters)} clusters:")
        for cluster in clusters:
            logger.info(f"   ├─ {cluster['id']}: {cluster['gene_count']} genes")

        return {
            "success": True,
            "clusters": clusters,
            "total": len(clusters),
            "output_dir": output_dir
        }

    except subprocess.TimeoutExpired:
        logger.error(f"❌ [CLUSTERING] Execution timeout (>10 minutes)")
        return {
            "success": False,
            "error": "Clustering execution timeout (>10 minutes)"
        }
    except Exception as e:
        logger.exception(f"❌ [CLUSTERING] Unexpected error")
        return {
            "success": False,
            "error": str(e)
        }


def run_mfuzz_clustering_docker(workbench_id: int, source_type: str,
                                 p_value: float = None, fold_change: float = None,
                                 top_n_genes: int = 8000,
                                 cluster_count: int = 6, m_value: float = None,
                                 min_membership: float = 0.5):
    """
    Mfuzz fuzzy c-means clustering Docker 실행

    Args:
        workbench_id: 워크벤치 ID
        source_type: 'deg' | 'variance' | 'tmm'
        p_value: P-value cutoff (source_type='deg'인 경우)
        fold_change: Fold change cutoff (source_type='deg'인 경우)
        top_n_genes: Top N genes by MAD (source_type='variance'인 경우, default: 8000)
        cluster_count: 클러스터 개수 (default: 6)
        m_value: Fuzzification parameter (None이면 자동 추정)
        min_membership: Membership cutoff (default: 0.5)

    Returns:
        dict: {
            "success": bool,
            "clusters": list,
            "total": int,
            "output_dir": str,
            "parameters": dict,
            "error": str (실패 시)
        }
    """
    try:
        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return {
                "success": False,
                "error": "Workbench not found"
            }

        # 경로 설정
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        workbench_dir = workbench_schema['base']
        deg_dir = workbench_schema['deg']
        counts_dir = workbench_schema['quanti']['counts']

        # 스크립트 디렉토리 생성 및 복사
        script_dir = os.path.join(workbench_dir, 'script')
        os.makedirs(script_dir, exist_ok=True)

        # R 스크립트 복사 (VizR 컨테이너 → 워크벤치)
        import shutil
        source_script = os.path.join(os.path.dirname(__file__), '..', 'pipeline', 'scripts', 'run_mfuzz.R')
        dest_script = os.path.join(script_dir, 'run_mfuzz.R')
        shutil.copy2(source_script, dest_script)
        logger.info(f"📋 [MFUZZ] R script copied: {dest_script}")

        # source_type에 따라 분기
        if source_type == "deg":
            # ========== Option 1: DEG-filtered ==========
            matrix_name = f"diffExpr.P{p_value}_C{fold_change}.matrix.RData"
            matrix_path = os.path.join(deg_dir, 'edgeR', matrix_name)

            # Matrix 파일 존재 확인 및 자동 생성
            if not os.path.exists(matrix_path):
                logger.info(f"📁 [MFUZZ] DEG matrix not found, generating: {matrix_name}")

                # run_dea() 호출하여 파일 생성
                from backend.pipeline.utils.de_analysis import run_dea

                # TMM matrix 경로
                tmm_matrix_file = os.path.join(counts_dir, 'genes.TMM.matrix')

                # samples.txt 경로
                samples_dir = workbench_schema['quanti']['samples']
                samples_file = os.path.join(samples_dir, 'samples.txt')

                # 파일 존재 확인
                if not os.path.exists(tmm_matrix_file):
                    logger.error(f"❌ [MFUZZ] TMM matrix not found: {tmm_matrix_file}")
                    return {
                        "success": False,
                        "error": "TMM matrix file not found. Please run quantification first."
                    }

                if not os.path.exists(samples_file):
                    logger.error(f"❌ [MFUZZ] Samples file not found: {samples_file}")
                    return {
                        "success": False,
                        "error": "Samples file not found. Please run quantification first."
                    }

                # run_dea() 호출
                edger_dir = os.path.join(deg_dir, 'edgeR')
                dea_result = run_dea(
                    workbench_root=workbench_dir,
                    output_dir=edger_dir,
                    tmm_matrix_file=tmm_matrix_file,
                    samples_file=samples_file,
                    workbench_id=workbench_id,
                    worker_id="mfuzz_worker",
                    p_value=p_value,
                    fold_change=fold_change
                )

                if not dea_result.get('success', False):
                    error_msg = dea_result.get('error', 'Unknown error')
                    logger.error(f"❌ [MFUZZ] Failed to generate DEG matrix: {error_msg}")
                    return {
                        "success": False,
                        "error": f"Failed to generate DEG matrix: {error_msg}"
                    }

                logger.info(f"✅ [MFUZZ] DEG matrix generated successfully: {matrix_name}")
            else:
                logger.info(f"✅ [MFUZZ] Using existing DEG matrix: {matrix_name}")

            # 출력 디렉토리 설정
            output_dirname = f"mfuzz_deg_P{p_value}_C{fold_change}_c{cluster_count}_m{m_value if m_value else 'auto'}_mem{min_membership}"
            output_dir = os.path.join(deg_dir, 'edgeR', output_dirname)
            os.makedirs(output_dir, exist_ok=True)

            # Mfuzz 명령어 구성
            mfuzz_command = (
                f"Rscript /data/script/run_mfuzz.R "
                f"--source-type deg "
                f"--matrix /data/deg/edgeR/{matrix_name} "
                f"--clusters {cluster_count} "
                f"--min-membership {min_membership} "
                f"--output /data/deg/edgeR/{output_dirname}"
            )

        elif source_type == "variance":
            # ========== Option 2: Variance-filtered (recommended) ==========
            tmm_matrix_path = os.path.join(counts_dir, 'genes.TMM.matrix')

            # TMM matrix 파일 존재 확인
            if not os.path.exists(tmm_matrix_path):
                logger.error(f"❌ [MFUZZ] TMM matrix not found: {tmm_matrix_path}")
                return {
                    "success": False,
                    "error": "TMM matrix not found. Please run quantification first."
                }

            # 출력 디렉토리 설정
            output_dirname = f"mfuzz_variance_top{top_n_genes}_c{cluster_count}_m{m_value if m_value else 'auto'}_mem{min_membership}"
            output_dir = os.path.join(counts_dir, output_dirname)
            os.makedirs(output_dir, exist_ok=True)

            # Mfuzz 명령어 구성
            mfuzz_command = (
                f"Rscript /data/script/run_mfuzz.R "
                f"--source-type variance "
                f"--tmm-matrix /data/quanti/counts/genes.TMM.matrix "
                f"--top-n-genes {top_n_genes} "
                f"--clusters {cluster_count} "
                f"--min-membership {min_membership} "
                f"--output /data/quanti/counts/{output_dirname}"
            )

        elif source_type == "tmm":
            # ========== Option 3: Full TMM (not recommended) ==========
            tmm_matrix_path = os.path.join(counts_dir, 'genes.TMM.matrix')

            # TMM matrix 파일 존재 확인
            if not os.path.exists(tmm_matrix_path):
                logger.error(f"❌ [MFUZZ] TMM matrix not found: {tmm_matrix_path}")
                return {
                    "success": False,
                    "error": "TMM matrix not found. Please run quantification first."
                }

            # 출력 디렉토리 설정
            output_dirname = f"mfuzz_tmm_full_c{cluster_count}_m{m_value if m_value else 'auto'}_mem{min_membership}"
            output_dir = os.path.join(counts_dir, output_dirname)
            os.makedirs(output_dir, exist_ok=True)

            # Mfuzz 명령어 구성
            mfuzz_command = (
                f"Rscript /data/script/run_mfuzz.R "
                f"--source-type tmm "
                f"--tmm-matrix /data/quanti/counts/genes.TMM.matrix "
                f"--clusters {cluster_count} "
                f"--min-membership {min_membership} "
                f"--output /data/quanti/counts/{output_dirname}"
            )

        else:
            return {
                "success": False,
                "error": f"Invalid source_type: {source_type}. Must be 'deg', 'variance', or 'tmm'."
            }

        # m parameter 추가 (지정된 경우만)
        if m_value is not None:
            mfuzz_command += f" --m {m_value}"

        # 호스트 경로로 변환
        host_workbench_dir = workbench_dir.replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)
        logger.info(f"🔄 [MFUZZ] Path conversion: container→host")
        logger.info(f"   ├─ Container: {workbench_dir}")
        logger.info(f"   └─ Host: {host_workbench_dir}")

        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_workbench_dir}:/data",
            "-w", "/data",
            SharedConfig.TRINITY_IMAGE,
            "bash", "-c",
            mfuzz_command
        ]

        # 실행
        logger.info(f"🚀 [MFUZZ] Running Mfuzz clustering:")
        logger.info(f"├─ Workbench: {workbench['name']} (ID: {workbench_id})")
        logger.info(f"├─ Source type: {source_type}")
        if source_type == "deg":
            logger.info(f"├─ P-value: {p_value}")
            logger.info(f"├─ Fold Change: {fold_change}")
        elif source_type == "variance":
            logger.info(f"├─ Top N genes: {top_n_genes}")
        logger.info(f"├─ Clusters: {cluster_count}")
        logger.info(f"├─ Fuzzification (m): {m_value if m_value else 'auto'}")
        logger.info(f"├─ Min membership: {min_membership}")
        # bash -c 이후 명령어는 따옴표로 감싸서 출력
        import shlex
        cmd_display = ' '.join(shlex.quote(arg) for arg in docker_cmd)
        logger.info(f"└─ Command: {cmd_display}")

        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10분 타임아웃
        )

        if result.returncode != 0:
            logger.error(f"❌ [MFUZZ] Docker execution failed:")
            logger.error(f"   └─ stderr: {result.stderr}")
            return {
                "success": False,
                "error": f"Mfuzz clustering failed: {result.stderr}"
            }

        logger.info(f"✅ [MFUZZ] Docker execution completed")

        # 결과 수집
        if not os.path.exists(output_dir):
            logger.error(f"❌ [MFUZZ] Output directory not created: {output_dir}")
            return {
                "success": False,
                "error": "Mfuzz output directory not found"
            }

        cluster_files = sorted(glob.glob(os.path.join(output_dir, "cluster_*.tsv")))

        # 클러스터 메타데이터 생성 (cluster_N.tsv 형식만, centroids 제외)
        clusters = []
        for file_path in cluster_files:
            filename = os.path.basename(file_path)
            # cluster_N.tsv 형식만 처리 (cluster_centroids.tsv 제외)
            try:
                cluster_num = int(filename.split('_')[1].split('.')[0])
            except ValueError:
                # 숫자가 아니면 건너뛰기 (예: cluster_centroids.tsv)
                continue

            # 유전자 수 계산 (헤더 제외)
            with open(file_path, 'r', encoding='utf-8') as f:
                gene_count = sum(1 for line in f) - 1

            clusters.append({
                "id": cluster_num,
                "gene_count": gene_count,
                "file_name": filename
            })

        if not clusters:
            logger.warning(f"⚠️ [MFUZZ] No cluster files generated")
            return {
                "success": False,
                "error": "No cluster files generated. Try lowering min_membership cutoff."
            }

        # ID로 정렬
        clusters.sort(key=lambda x: x['id'])

        logger.info(f"✅ [MFUZZ] Generated {len(clusters)} clusters:")
        for cluster in clusters:
            logger.info(f"   ├─ Cluster {cluster['id']}: {cluster['gene_count']} genes")

        return {
            "success": True,
            "clusters": clusters,
            "total": len(clusters),
            "output_dir": output_dir,
            "parameters": {
                "source_type": source_type,
                "cluster_count": cluster_count,
                "m_value": m_value,
                "min_membership": min_membership,
                "p_value": p_value if source_type == "deg" else None,
                "fold_change": fold_change if source_type == "deg" else None,
                "top_n_genes": top_n_genes if source_type == "variance" else None
            }
        }

    except subprocess.TimeoutExpired:
        logger.error(f"❌ [MFUZZ] Execution timeout (>10 minutes)")
        return {
            "success": False,
            "error": "Mfuzz clustering timeout (>10 minutes)"
        }
    except Exception as e:
        logger.exception(f"❌ [MFUZZ] Unexpected error")
        return {
            "success": False,
            "error": str(e)
        }


def parse_cluster_matrix(file_path: str) -> dict:
    """
    클러스터 matrix 파일 파싱

    Args:
        file_path: matrix 파일 경로

    Returns:
        dict: {
            "genes": list,
            "samples": list,
            "statistics": dict
        }
    """
    try:
        # 파일 읽기 (탭 구분, UTF-8)
        df = pd.read_csv(file_path, sep='\t', index_col=0, encoding='utf-8')

        logger.info(f"🔍 [CLUSTERING][DEBUG] matrix file: {file_path}")
        logger.info(f"🔍 [CLUSTERING][DEBUG] sample columns order: {df.columns.tolist()}")

        # Gene annotations 추가
        gene_annotations = load_gene_annotations()

        # 데이터 변환
        genes_data = []
        for gene_id, row in df.iterrows():
            gene_info = gene_annotations.get(gene_id, {})
            gene_dict = {
                "gene_id": gene_id,
                "gene_symbol": gene_info.get('symbol', gene_id),
                "gene_description": gene_info.get('description', 'No description available')
            }
            # 각 샘플의 값 추가
            for sample_name, value in row.items():
                gene_dict[sample_name] = float(value) if pd.notna(value) else 0.0

            genes_data.append(gene_dict)

        # 통계 계산
        stats = {
            "mean": df.mean(axis=0).tolist(),
            "median": df.median(axis=0).tolist(),
            "min": df.min(axis=0).tolist(),
            "max": df.max(axis=0).tolist()
        }

        return {
            "genes": genes_data,
            "samples": df.columns.tolist(),
            "statistics": stats
        }

    except Exception as e:
        logger.exception(f"❌ [CLUSTERING] Error parsing matrix file: {file_path}")
        raise


def parse_cluster_preview(file_path: str) -> dict:
    """
    Parse matrix file for lightweight preview statistics only.
    """
    try:
        df = pd.read_csv(file_path, sep='\t', index_col=0, encoding='utf-8')
        numeric_df = df.apply(pd.to_numeric, errors='coerce').fillna(0.0)
        return {
            "gene_count": len(numeric_df.index),
            "samples": numeric_df.columns.tolist(),
            "statistics": {
                "mean": numeric_df.mean(axis=0).tolist(),
                "median": numeric_df.median(axis=0).tolist()
            }
        }
    except Exception:
        logger.exception(f"❌ [CLUSTERING] Error parsing preview matrix file: {file_path}")
        raise


def reorder_preview_by_samples_file(workbench_schema: dict, preview: dict) -> dict:
    """
    Reorder preview sample axis by quanti/samples/samples.txt order.
    """
    samples_file = os.path.join(workbench_schema['quanti']['samples'], 'samples.txt')
    if not os.path.exists(samples_file):
        return preview

    try:
        with open(samples_file, 'r', encoding='utf-8') as f:
            sample_order = [line.strip().split('\t')[1] for line in f if line.strip()]

        file_samples = set(preview['samples'])
        ordered_samples = [s for s in sample_order if s in file_samples]
        if not ordered_samples:
            return preview

        idx_map = {s: i for i, s in enumerate(preview['samples'])}
        reorder_idx = [idx_map[s] for s in ordered_samples if s in idx_map]
        preview['samples'] = ordered_samples
        for key in preview['statistics']:
            preview['statistics'][key] = [preview['statistics'][key][i] for i in reorder_idx]
    except Exception as e:
        logger.warning(f"⚠️ [CLUSTERING] Failed to reorder preview by samples.txt: {e}")

    return preview


def get_tree_cluster_output_dir(workbench_schema: dict, p_value: float, fold_change: float, ptree: int) -> str:
    deg_dir = workbench_schema['deg']
    matrix_name = f"diffExpr.P{p_value}_C{fold_change}.matrix.RData"
    return os.path.join(deg_dir, 'edgeR', f"{matrix_name}.clusters_fixed_P_{ptree}")


def _sort_cluster_file_paths(file_paths: list[str]) -> list[str]:
    def cluster_key(path: str) -> int:
        name = os.path.basename(path)
        cluster_id = name.replace("_log2_medianCentered_fpkm.matrix", "")
        try:
            return int(cluster_id.replace("subcluster_", ""))
        except Exception:
            return 10**9
    return sorted(file_paths, key=cluster_key)


def _ptree_to_cutline_y(ptree: int, y_min: float, y_max: float) -> float:
    ptree_clamped = max(1, min(100, int(ptree)))
    if y_max <= y_min:
        return float(y_min)
    ratio = float(ptree_clamped - 1) / 99.0
    return float(y_min + ratio * (y_max - y_min))


def build_tree_cluster_dendrogram(workbench_schema: dict, p_value: float, fold_change: float, ptree: int) -> dict:
    """
    Build dendrogram data from tree-cutting cluster mean patterns.
    """
    output_dir = get_tree_cluster_output_dir(workbench_schema, p_value, fold_change, ptree)
    if not os.path.exists(output_dir):
        return {
            "exists": False,
            "status": "not_available"
        }

    matrix_files = _sort_cluster_file_paths(glob.glob(os.path.join(output_dir, "subcluster_*.matrix")))
    if not matrix_files:
        return {
            "exists": False,
            "status": "not_available"
        }

    clusters: list[str] = []
    vectors: list[np.ndarray] = []
    samples: list[str] = []
    for file_path in matrix_files:
        cluster_id = os.path.basename(file_path).replace("_log2_medianCentered_fpkm.matrix", "")
        preview = parse_cluster_preview(file_path)
        preview = reorder_preview_by_samples_file(workbench_schema, preview)
        mean_vector = np.array(preview["statistics"]["mean"], dtype=float)
        if mean_vector.size == 0:
            continue

        if not samples:
            samples = preview["samples"]
        elif len(preview["samples"]) != len(samples):
            min_len = min(len(samples), len(preview["samples"]), mean_vector.size)
            samples = samples[:min_len]
            mean_vector = mean_vector[:min_len]
            vectors = [v[:min_len] for v in vectors]
        elif mean_vector.size != len(samples):
            mean_vector = mean_vector[:len(samples)]

        clusters.append(cluster_id)
        vectors.append(mean_vector)

    if len(clusters) < 2:
        return {
            "exists": True,
            "status": "insufficient_clusters",
            "clusters": clusters,
            "samples": samples,
            "method": {
                "distance": "1-pearson",
                "linkage": "average"
            }
        }

    matrix = np.vstack(vectors)

    with np.errstate(invalid='ignore'):
        corr = np.corrcoef(matrix)
    corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
    corr = np.clip(corr, -1.0, 1.0)
    distance_matrix = 1.0 - corr
    distance_matrix = (distance_matrix + distance_matrix.T) / 2.0
    np.fill_diagonal(distance_matrix, 0.0)

    condensed = squareform(distance_matrix, checks=False)
    linkage_matrix = hierarchy.linkage(condensed, method='average')
    dendro = hierarchy.dendrogram(linkage_matrix, no_plot=True)
    leaf_order = [int(idx) for idx in dendro["leaves"]]
    icoord = [[float(value) for value in coords] for coords in dendro["icoord"]]
    dcoord = [[float(value) for value in coords] for coords in dendro["dcoord"]]
    color_list = [str(color) for color in dendro.get("color_list", [])]

    dcoord_values = [value for coords in dcoord for value in coords]
    y_min = float(min(dcoord_values)) if dcoord_values else 0.0
    y_max = float(max(dcoord_values)) if dcoord_values else 0.0
    cutline_y = _ptree_to_cutline_y(ptree, y_min, y_max)

    return {
        "exists": True,
        "status": "available",
        "method": {
            "distance": "1-pearson",
            "linkage": "average"
        },
        "clusters": clusters,
        "samples": samples,
        "leaf_order": leaf_order,
        "dendrogram": {
            "icoord": icoord,
            "dcoord": dcoord,
            "color_list": color_list
        },
        "y_range": {
            "min": y_min,
            "max": y_max
        },
        "cutline": {
            "ptree": int(max(1, min(100, ptree))),
            "y": cutline_y
        }
    }


def load_merged_tree_cluster_df(workbench_schema: dict, p_value: float, fold_change: float, ptree: int, cluster_ids: list[str]) -> pd.DataFrame:
    """
    Load multiple tree cluster matrix files, union genes by gene_id, and return a merged DataFrame.
    """
    output_dir = get_tree_cluster_output_dir(workbench_schema, p_value, fold_change, ptree)
    if not os.path.exists(output_dir):
        raise FileNotFoundError(f"Tree clustering output directory not found: {output_dir}")

    frames = []
    for cluster_id in cluster_ids:
        file_path = os.path.join(output_dir, f"{cluster_id}_log2_medianCentered_fpkm.matrix")
        if not os.path.exists(file_path):
            logger.warning(f"⚠️ [CLUSTERING] Merge source file not found: {file_path}")
            continue
        df = pd.read_csv(file_path, sep='\t', index_col=0, encoding='utf-8')
        frames.append(df)

    if not frames:
        raise FileNotFoundError("No valid source cluster files found for merge")

    merged_df = pd.concat(frames, axis=0)
    # Keep first occurrence when duplicate gene IDs exist across source clusters.
    merged_df = merged_df[~merged_df.index.duplicated(keep='first')]
    merged_df = merged_df.apply(pd.to_numeric, errors='coerce').fillna(0.0)

    # Reorder columns by samples.txt if possible.
    samples_file = os.path.join(workbench_schema['quanti']['samples'], 'samples.txt')
    if os.path.exists(samples_file):
        try:
            with open(samples_file, 'r', encoding='utf-8') as f:
                sample_order = [line.strip().split('\t')[1] for line in f if line.strip()]
            ordered_samples = [s for s in sample_order if s in merged_df.columns]
            if ordered_samples:
                merged_df = merged_df[ordered_samples]
        except Exception as e:
            logger.warning(f"⚠️ [CLUSTERING] Failed to reorder merged columns by samples.txt: {e}")

    return merged_df


def build_cluster_data_from_df(df: pd.DataFrame) -> dict:
    """
    Build Tree cluster response-compatible structure from a DataFrame.
    """
    gene_annotations = load_gene_annotations()

    genes_data = []
    for gene_id, row in df.iterrows():
        gene_info = gene_annotations.get(gene_id, {})
        gene_dict = {
            "gene_id": gene_id,
            "gene_symbol": gene_info.get('symbol', gene_id),
            "gene_description": gene_info.get('description', 'No description available')
        }
        for sample_name, value in row.items():
            gene_dict[sample_name] = float(value) if pd.notna(value) else 0.0
        genes_data.append(gene_dict)

    stats = {
        "mean": df.mean(axis=0).tolist(),
        "median": df.median(axis=0).tolist(),
        "min": df.min(axis=0).tolist(),
        "max": df.max(axis=0).tolist()
    }

    return {
        "genes": genes_data,
        "samples": df.columns.tolist(),
        "statistics": stats
    }


@clustering_bp.route('/<int:workbench_id>/clustering/tree-cutting/run', methods=['POST'])
def run_clustering(workbench_id: int):
    """
    클러스터링 실행

    Request Body:
        {
            "p_value": 0.1,
            "fold_change": 1.0,
            "ptree": 30
        }

    Response:
        {
            "success": true,
            "clusters": [
                {"id": "subcluster_1", "gene_count": 150, "file_name": "..."},
                ...
            ],
            "total": 7,
            "output_dir": "..."
        }
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        p_value = float(data.get('p_value', 0.1))
        fold_change = float(data.get('fold_change', 1.0))
        ptree = int(data.get('ptree', 30))

        logger.info(f"📊 [CLUSTERING] Run request:")
        logger.info(f"├─ Workbench ID: {workbench_id}")
        logger.info(f"├─ P-value: {p_value}")
        logger.info(f"├─ Fold Change: {fold_change}")
        logger.info(f"└─ Ptree: {ptree}")

        # Docker 실행
        result = run_tree_clustering_docker(workbench_id, p_value, fold_change, ptree)

        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.exception(f"❌ [CLUSTERING] Run failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/tree-cutting/clusters', methods=['GET'])
def get_clusters(workbench_id: int):
    """
    클러스터 목록 조회 (캐시된 결과, 없으면 자동 실행)

    Query Parameters:
        p_value: P-value cutoff (default: 0.1)
        fold_change: Fold change cutoff (default: 1.0)
        ptree: Ptree parameter (default: 30)
        auto_run: 자동 실행 여부 (default: true)
        search: 검색어 (유전자 ID 또는 Symbol, 부분 일치, 대소문자 구분 없음)

    Response:
        {
            "exists": true,
            "clusters": [
                {"id": "subcluster_1", "gene_count": 150, "file_name": "..."},
                ...
            ],
            "total": 7,
            "is_search_result": false,
            "search_query": ""
        }
    """
    try:
        p_value = float(request.args.get('p_value', 0.1))
        fold_change = float(request.args.get('fold_change', 1.0))
        ptree = int(request.args.get('ptree', 30))
        auto_run = request.args.get('auto_run', 'true').lower() == 'true'
        search_query = request.args.get('search', '').strip()

        logger.debug(f"🔍 [CLUSTERING] Get clusters request:")
        logger.debug(f"├─ Workbench ID: {workbench_id}")
        logger.debug(f"├─ P-value: {p_value}")
        logger.debug(f"├─ Fold Change: {fold_change}")
        logger.debug(f"├─ Ptree: {ptree}")
        logger.debug(f"├─ Auto run: {auto_run}")
        logger.debug(f"└─ Search: {search_query if search_query else 'None'}")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        # 결과 디렉토리 확인
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']

        matrix_name = f"diffExpr.P{p_value}_C{fold_change}.matrix.RData"
        output_dir = os.path.join(deg_dir, 'edgeR', f"{matrix_name}.clusters_fixed_P_{ptree}")

        if not os.path.exists(output_dir):
            logger.info(f"ℹ️ [CLUSTERING] No cached results found")

            # 자동 실행이 활성화된 경우
            if auto_run:
                logger.info(f"🤖 [CLUSTERING] Auto-running tree clustering with default parameters...")

                # Docker 실행
                result = run_tree_clustering_docker(workbench_id, p_value, fold_change, ptree)

                if result['success']:
                    logger.info(f"✅ [CLUSTERING] Auto-run completed: {len(result['clusters'])} clusters")
                    return jsonify({
                        "exists": True,
                        "clusters": result['clusters'],
                        "total": result['total']
                    }), 200
                else:
                    logger.error(f"❌ [CLUSTERING] Auto-run failed: {result.get('error')}")
                    return jsonify({"exists": False, "clusters": [], "total": 0, "error": result.get('error')}), 200

            return jsonify({"exists": False, "clusters": [], "total": 0}), 200

        # 클러스터 파일 수집
        matrix_files = sorted(glob.glob(os.path.join(output_dir, "subcluster_*.matrix")))

        # 검색어가 있을 경우 gene_annotations 로드
        gene_annotations = {}
        if search_query:
            try:
                gene_annotations = load_gene_annotations()
            except Exception as e:
                logger.warning(f"⚠️ [CLUSTERING] Failed to load gene annotations: {e}")
                gene_annotations = {}

        clusters = []
        for file_path in matrix_files:
            filename = os.path.basename(file_path)
            cluster_id = filename.replace("_log2_medianCentered_fpkm.matrix", "")

            # 검색어가 있을 경우 클러스터 내 유전자 검색
            if search_query:
                import re
                search_terms = [term.strip().upper() for term in re.split(r'[,\s\t\n]+', search_query) if term.strip()]
                cluster_contains_search = False

                try:
                    data = parse_cluster_matrix(file_path)
                    genes_list = data.get('genes', [])

                    for gene in genes_list:
                        gene_id = gene.get('gene_id', '').upper()
                        gene_symbol = gene.get('gene_symbol', gene_id).upper()

                        # gene_id 또는 gene_symbol 부분 일치 검색
                        for term in search_terms:
                            if term in gene_id or term in gene_symbol:
                                cluster_contains_search = True
                                break

                        if cluster_contains_search:
                            break

                    # gene_annotations 추가 검색
                    if not cluster_contains_search and gene_annotations:
                        for gene in genes_list:
                            gene_info = gene_annotations.get(gene.get('gene_id', ''), {})
                            symbol = gene_info.get('symbol', '').upper()
                            if any(term in symbol for term in search_terms):
                                cluster_contains_search = True
                                break

                except Exception as e:
                    logger.warning(f"⚠️ [CLUSTERING] Failed to search in cluster {cluster_id}: {e}")
                    continue

                if not cluster_contains_search:
                    continue

            with open(file_path, 'r', encoding='utf-8') as f:
                gene_count = sum(1 for line in f) - 1

            clusters.append({
                "id": cluster_id,
                "gene_count": gene_count,
                "file_name": filename
            })

        logger.debug(f"✅ [CLUSTERING] Found {len(clusters)} cached clusters{' (search: ' + search_query + ')' if search_query else ''}")

        return jsonify({
            "exists": True,
            "clusters": clusters,
            "total": len(clusters),
            "is_search_result": bool(search_query),
            "search_query": search_query
        }), 200

    except Exception as e:
        logger.exception(f"❌ [CLUSTERING] Get clusters failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/tree-cutting/previews', methods=['GET'])
def get_cluster_previews(workbench_id: int):
    """
    Get lightweight pattern previews for multiple clusters in one request.

    Query Parameters:
        p_value: float
        fold_change: float
        ptree: int
        cluster_ids: comma-separated cluster IDs
    """
    try:
        p_value = float(request.args.get('p_value', 0.1))
        fold_change = float(request.args.get('fold_change', 1.0))
        ptree = int(request.args.get('ptree', 30))
        cluster_ids_raw = request.args.get('cluster_ids', '').strip()

        if not cluster_ids_raw:
            return jsonify({'error': 'cluster_ids is required'}), 400

        cluster_ids = [cluster_id.strip() for cluster_id in cluster_ids_raw.split(',') if cluster_id.strip()]
        if not cluster_ids:
            return jsonify({'error': 'cluster_ids is empty'}), 400

        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']

        matrix_name = f"diffExpr.P{p_value}_C{fold_change}.matrix.RData"
        output_dir = os.path.join(deg_dir, 'edgeR', f"{matrix_name}.clusters_fixed_P_{ptree}")

        if not os.path.exists(output_dir):
            return jsonify({"exists": False, "previews": [], "total": 0}), 200

        previews = []
        for cluster_id in cluster_ids:
            file_path = os.path.join(output_dir, f"{cluster_id}_log2_medianCentered_fpkm.matrix")
            if not os.path.exists(file_path):
                continue

            preview = parse_cluster_preview(file_path)
            preview = reorder_preview_by_samples_file(workbench_schema, preview)

            previews.append({
                "id": cluster_id,
                "gene_count": preview['gene_count'],
                "samples": preview['samples'],
                "statistics": preview['statistics']
            })

        return jsonify({
            "exists": True,
            "previews": previews,
            "total": len(previews)
        }), 200

    except Exception as e:
        logger.exception("❌ [CLUSTERING] Get cluster previews failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/tree-cutting/dendrogram', methods=['GET'])
def get_tree_cutting_dendrogram(workbench_id: int):
    """
    Get cluster-level dendrogram data for tree-cutting overview.
    """
    try:
        p_value = float(request.args.get('p_value', 0.1))
        fold_change = float(request.args.get('fold_change', 1.0))
        ptree = int(request.args.get('ptree', 30))

        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        result = build_tree_cluster_dendrogram(workbench_schema, p_value, fold_change, ptree)
        return jsonify(result), 200
    except Exception as e:
        logger.exception("❌ [CLUSTERING] Get tree dendrogram failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/tree-cutting/merged-preview', methods=['GET'])
def get_merged_cluster_preview(workbench_id: int):
    """
    Get merged preview statistics for selected source clusters.
    """
    try:
        p_value = float(request.args.get('p_value', 0.1))
        fold_change = float(request.args.get('fold_change', 1.0))
        ptree = int(request.args.get('ptree', 30))
        merged_id = request.args.get('merged_id', 'merged_preview')
        cluster_ids_raw = request.args.get('cluster_ids', '').strip()

        if not cluster_ids_raw:
            return jsonify({'error': 'cluster_ids is required'}), 400

        cluster_ids = [cluster_id.strip() for cluster_id in cluster_ids_raw.split(',') if cluster_id.strip()]
        if len(cluster_ids) < 2:
            return jsonify({'error': 'At least 2 cluster_ids are required'}), 400

        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        merged_df = load_merged_tree_cluster_df(workbench_schema, p_value, fold_change, ptree, cluster_ids)

        return jsonify({
            "exists": True,
            "preview": {
                "id": merged_id,
                "source_cluster_ids": cluster_ids,
                "gene_count": int(len(merged_df.index)),
                "samples": merged_df.columns.tolist(),
                "statistics": {
                    "mean": merged_df.mean(axis=0).tolist(),
                    "median": merged_df.median(axis=0).tolist()
                }
            }
        }), 200
    except FileNotFoundError as e:
        logger.error(f"❌ [CLUSTERING] Merged preview failed: {e}")
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.exception("❌ [CLUSTERING] Get merged preview failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/tree-cutting/merged-data', methods=['GET'])
def get_merged_cluster_data(workbench_id: int):
    """
    Get merged cluster data with search and pagination.
    """
    try:
        p_value = float(request.args.get('p_value', 0.1))
        fold_change = float(request.args.get('fold_change', 1.0))
        ptree = int(request.args.get('ptree', 30))
        merged_id = request.args.get('merged_id', 'merged')
        cluster_ids_raw = request.args.get('cluster_ids', '').strip()
        search_query = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 500))

        if not cluster_ids_raw:
            return jsonify({'error': 'cluster_ids is required'}), 400

        cluster_ids = [cluster_id.strip() for cluster_id in cluster_ids_raw.split(',') if cluster_id.strip()]
        if len(cluster_ids) < 2:
            return jsonify({'error': 'At least 2 cluster_ids are required'}), 400

        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        merged_df = load_merged_tree_cluster_df(workbench_schema, p_value, fold_change, ptree, cluster_ids)
        data = build_cluster_data_from_df(merged_df)

        genes_list = data['genes']
        if search_query:
            import re
            search_terms = [term.strip().upper() for term in re.split(r'[,\s\t\n]+', search_query) if term.strip()]
            if search_terms:
                filtered_genes = []
                for gene in genes_list:
                    gene_id = gene['gene_id']
                    gene_symbol = gene.get('gene_symbol', gene_id)
                    matched = any(term in gene_id.upper() or term in gene_symbol.upper() for term in search_terms)
                    if matched:
                        filtered_genes.append(gene)
                genes_list = filtered_genes

        filtered_total = len(genes_list)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_genes = genes_list[start_idx:end_idx]
        total_pages = (filtered_total + limit - 1) // limit if filtered_total > 0 else 1

        return jsonify({
            'cluster_id': merged_id,
            'source_cluster_ids': cluster_ids,
            'gene_count': filtered_total,
            'total_genes': filtered_total,
            'showing_genes': len(paginated_genes),
            'current_page': page,
            'total_pages': total_pages,
            'page_size': limit,
            'genes': paginated_genes,
            'samples': data['samples'],
            'statistics': data['statistics'],
            'is_search_result': bool(search_query),
            'search_query': search_query
        }), 200
    except FileNotFoundError as e:
        logger.error(f"❌ [CLUSTERING] Merged data failed: {e}")
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.exception("❌ [CLUSTERING] Get merged data failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/tree-cutting/cluster/<cluster_id>', methods=['GET'])
def get_cluster_data(workbench_id: int, cluster_id: str):
    """
    특정 클러스터 데이터 조회

    Query Parameters:
        p_value: P-value cutoff (default: 0.1)
        fold_change: Fold change cutoff (default: 1.0)
        ptree: Ptree parameter (default: 30)
        search: 검색어 (부분 일치, 대소문자 구분 없음)
        page: 페이지 번호 (default: 1)
        limit: 페이지당 항목 수 (default: 500)

    Response:
        {
            "cluster_id": "subcluster_1",
            "total_genes": 150,
            "showing_genes": 100,
            "current_page": 1,
            "total_pages": 2,
            "page_size": 100,
            "genes": [
                {
                    "gene_id": "TRINITY_DN1000_c0_g1",
                    "gene_symbol": "NAC001",
                    "sample1": 5.2,
                    "sample2": 6.1,
                    ...
                },
                ...
            ],
            "samples": ["sample1", "sample2", ...],
            "statistics": {
                "mean": [5.5, 6.0, ...],
                "median": [5.4, 5.9, ...],
                "min": [2.1, 2.5, ...],
                "max": [8.9, 9.2, ...]
            },
            "is_search_result": false,
            "search_query": ""
        }
    """
    try:
        p_value = float(request.args.get('p_value', 0.1))
        fold_change = float(request.args.get('fold_change', 1.0))
        ptree = int(request.args.get('ptree', 30))

        # 검색 및 페이지네이션 파라미터
        search_query = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 500))

        logger.info(f"📊 [CLUSTERING] Get cluster data:")
        logger.info(f"├─ Workbench ID: {workbench_id}")
        logger.info(f"├─ Cluster ID: {cluster_id}")
        logger.info(f"├─ P-value: {p_value}")
        logger.info(f"├─ Fold Change: {fold_change}")
        logger.info(f"├─ Ptree: {ptree}")
        logger.info(f"├─ Search: {search_query if search_query else 'None'}")
        logger.info(f"└─ Page: {page}, Limit: {limit}")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        # 파일 경로
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']

        matrix_name = f"diffExpr.P{p_value}_C{fold_change}.matrix.RData"
        output_dir = os.path.join(deg_dir, 'edgeR', f"{matrix_name}.clusters_fixed_P_{ptree}")
        file_path = os.path.join(output_dir, f"{cluster_id}_log2_medianCentered_fpkm.matrix")

        if not os.path.exists(file_path):
            logger.error(f"❌ [CLUSTERING] Cluster file not found: {file_path}")
            return jsonify({"error": "Cluster file not found"}), 404

        # 파싱
        logger.info(f"📖 [CLUSTERING] Parsing cluster file: {file_path}")
        data = parse_cluster_matrix(file_path)

        # samples.txt 순서로 컬럼 재정렬
        samples_file = os.path.join(workbench_schema['quanti']['samples'], 'samples.txt')
        if os.path.exists(samples_file):
            try:
                with open(samples_file, 'r', encoding='utf-8') as f:
                    sample_order = [line.strip().split('\t')[1] for line in f if line.strip()]

                file_samples = set(data['samples'])
                ordered_samples = [s for s in sample_order if s in file_samples]

                if ordered_samples:
                    original_order = data['samples']
                    idx_map = {s: i for i, s in enumerate(original_order)}
                    reorder_idx = [idx_map[s] for s in ordered_samples if s in idx_map]

                    data['samples'] = ordered_samples
                    for key in data['statistics']:
                        data['statistics'][key] = [data['statistics'][key][i] for i in reorder_idx]

                    logger.info(f"🔍 [CLUSTERING][DEBUG] reordered samples: {ordered_samples}")
                else:
                    logger.warning(f"⚠️ [CLUSTERING] No matching samples found in samples.txt, using file order")
            except Exception as e:
                logger.warning(f"⚠️ [CLUSTERING] Failed to reorder by samples.txt: {e}")
        else:
            logger.warning(f"⚠️ [CLUSTERING] samples.txt not found: {samples_file}")

        # Gene annotations
        gene_annotations = load_gene_annotations()

        # DataFrame 생성 (검색 및 페이지네이션을 위해)
        genes_list = data['genes']
        total_genes = len(genes_list)

        # 검색 필터 적용
        if search_query:
            # 검색어를 쉼표, 공백, 탭, 줄바꿈으로 분리
            import re
            search_terms = [term.strip().upper() for term in re.split(r'[,\s\t\n]+', search_query) if term.strip()]

            logger.info(f"🔍 [CLUSTERING] Searching for: {search_terms}")

            if search_terms:
                filtered_genes = []
                for gene in genes_list:
                    gene_id = gene['gene_id']
                    gene_symbol = gene.get('gene_symbol', gene_id)

                    # gene_id 또는 gene_symbol에서 부분 일치 검색
                    match = False
                    for term in search_terms:
                        if term in gene_id.upper() or term in gene_symbol.upper():
                            match = True
                            break

                    if match:
                        filtered_genes.append(gene)

                genes_list = filtered_genes
                logger.info(f"🔍 [CLUSTERING] Search results: {len(genes_list)} genes")

        # 총 검색 결과 수
        filtered_total = len(genes_list)

        # 페이지네이션 적용
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_genes = genes_list[start_idx:end_idx]

        # 총 페이지 수 계산
        total_pages = (filtered_total + limit - 1) // limit if filtered_total > 0 else 1

        response = {
            'cluster_id': cluster_id,
            'gene_count': filtered_total,  # 하위 호환성 (기존 코드용)
            'total_genes': filtered_total,
            'showing_genes': len(paginated_genes),
            'current_page': page,
            'total_pages': total_pages,
            'page_size': limit,
            'genes': paginated_genes,
            'samples': data['samples'],
            'statistics': data['statistics'],
            'is_search_result': bool(search_query),
            'search_query': search_query
        }

        logger.info(f"✅ [CLUSTERING] Cluster data retrieved: {len(paginated_genes)} genes (page {page}/{total_pages}), {len(data['samples'])} samples")

        return jsonify(response), 200

    except Exception as e:
        logger.exception(f"❌ [CLUSTERING] Get cluster data failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/tree-cutting/download/<cluster_id>', methods=['GET'])
def download_cluster(workbench_id: int, cluster_id: str):
    """
    클러스터 데이터 다운로드

    Query Parameters:
        p_value: P-value cutoff (default: 0.1)
        fold_change: Fold change cutoff (default: 1.0)
        ptree: Ptree parameter (default: 30)
        format: tsv (default)

    Response:
        TSV 파일 다운로드
    """
    try:
        p_value = float(request.args.get('p_value', 0.1))
        fold_change = float(request.args.get('fold_change', 1.0))
        ptree = int(request.args.get('ptree', 30))

        logger.info(f"📥 [CLUSTERING] Download cluster:")
        logger.info(f"├─ Workbench ID: {workbench_id}")
        logger.info(f"└─ Cluster ID: {cluster_id}")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        # 파일 경로
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']

        matrix_name = f"diffExpr.P{p_value}_C{fold_change}.matrix.RData"
        output_dir = os.path.join(deg_dir, 'edgeR', f"{matrix_name}.clusters_fixed_P_{ptree}")
        file_path = os.path.join(output_dir, f"{cluster_id}_log2_medianCentered_fpkm.matrix")

        if not os.path.exists(file_path):
            logger.error(f"❌ [CLUSTERING] File not found: {file_path}")
            return jsonify({"error": "File not found"}), 404

        logger.info(f"✅ [CLUSTERING] Sending file: {cluster_id}.tsv")

        return send_file(
            file_path,
            as_attachment=True,
            download_name=f"{cluster_id}.tsv",
            mimetype='text/tab-separated-values'
        )

    except Exception as e:
        logger.exception(f"❌ [CLUSTERING] Download failed")
        return jsonify({'error': str(e)}), 500


# ==================== Mfuzz Clustering APIs ====================

def parse_mfuzz_cluster_preview(file_path: str) -> dict:
    """
    Parse Mfuzz cluster TSV for lightweight preview statistics only.
    """
    try:
        df = pd.read_csv(file_path, sep='\t', encoding='utf-8')
        sample_cols = [col for col in df.columns if col not in ['gene_id', 'membership']]
        numeric_df = df[sample_cols].apply(pd.to_numeric, errors='coerce').fillna(0.0)
        return {
            "gene_count": len(df.index),
            "samples": sample_cols,
            "statistics": {
                "mean": numeric_df.mean(axis=0).tolist(),
                "median": numeric_df.median(axis=0).tolist()
            }
        }
    except Exception:
        logger.exception(f"❌ [MFUZZ] Error parsing preview cluster file: {file_path}")
        raise

@clustering_bp.route('/<int:workbench_id>/clustering/mfuzz/run', methods=['POST'])
def run_mfuzz(workbench_id: int):
    """
    Mfuzz 클러스터링 실행

    Request Body:
        {
            "source_type": "deg" | "variance" | "tmm",
            "p_value": 0.05,           # source_type='deg'인 경우
            "fold_change": 2.0,         # source_type='deg'인 경우
            "top_n_genes": 8000,        # source_type='variance'인 경우
            "cluster_count": 6,
            "m_value": null,            # null이면 자동 추정
            "min_membership": 0.5
        }

    Response:
        {
            "success": true,
            "clusters": [
                {"id": 1, "gene_count": 150, "file_name": "cluster_1.tsv"},
                ...
            ],
            "total": 6,
            "output_dir": "...",
            "parameters": {...}
        }
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        source_type = data.get('source_type', 'deg')
        p_value = data.get('p_value')
        fold_change = data.get('fold_change')
        top_n_genes = int(data.get('top_n_genes', 8000))
        cluster_count = int(data.get('cluster_count', 6))
        m_value = data.get('m_value')  # None or float
        min_membership = float(data.get('min_membership', 0.5))

        # Convert to float if provided
        if p_value is not None:
            p_value = float(p_value)
        if fold_change is not None:
            fold_change = float(fold_change)
        if m_value is not None:
            m_value = float(m_value)

        logger.info(f"📊 [MFUZZ] Run request:")
        logger.info(f"├─ Workbench ID: {workbench_id}")
        logger.info(f"├─ Source type: {source_type}")
        if source_type == "deg":
            logger.info(f"├─ P-value: {p_value}")
            logger.info(f"├─ Fold Change: {fold_change}")
        elif source_type == "variance":
            logger.info(f"├─ Top N genes: {top_n_genes}")
        logger.info(f"├─ Cluster count: {cluster_count}")
        logger.info(f"├─ M value: {m_value if m_value else 'auto'}")
        logger.info(f"└─ Min membership: {min_membership}")

        # Docker 실행
        result = run_mfuzz_clustering_docker(
            workbench_id, source_type,
            p_value, fold_change, top_n_genes,
            cluster_count, m_value, min_membership
        )

        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400

    except Exception as e:
        logger.exception(f"❌ [MFUZZ] Run failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/mfuzz/clusters', methods=['GET'])
def get_mfuzz_clusters(workbench_id: int):
    """
    Mfuzz 클러스터 목록 조회 (캐시된 결과)

    Query Parameters:
        source_type: deg | variance | tmm (required)
        p_value: P-value cutoff (for deg only)
        fold_change: Fold change cutoff (for deg only)
        top_n_genes: Top N genes (for variance only)
        cluster_count: Cluster count (default: 6)
        m_value: M parameter (default: auto)
        min_membership: Min membership cutoff (default: 0.5)
        search: 검색어 (유전자 ID 또는 Symbol, 부분 일치, 대소문자 구분 없음)

    Response:
        {
            "exists": true,
            "clusters": [
                {"id": 1, "gene_count": 150, "file_name": "cluster_1.tsv"},
                ...
            ],
            "total": 6,
            "parameters": {...},
            "is_search_result": false,
            "search_query": ""
        }
    """
    try:
        source_type = request.args.get('source_type', 'deg')
        p_value = request.args.get('p_value')
        fold_change = request.args.get('fold_change')
        top_n_genes = request.args.get('top_n_genes')
        cluster_count = int(request.args.get('cluster_count', 6))
        m_value_param = request.args.get('m_value', 'auto')
        m_value = None if m_value_param == 'auto' else float(m_value_param)
        min_membership = float(request.args.get('min_membership', 0.5))
        search_query = request.args.get('search', '').strip()

        logger.info(f"🔍 [MFUZZ] Get clusters request:")
        logger.info(f"├─ Workbench ID: {workbench_id}")
        logger.info(f"├─ Source type: {source_type}")
        if source_type == 'deg':
            logger.info(f"├─ P-value: {p_value}")
            logger.info(f"├─ Fold Change: {fold_change}")
        elif source_type == 'variance':
            logger.info(f"├─ Top N genes: {top_n_genes}")
        logger.info(f"├─ Cluster count: {cluster_count}")
        logger.info(f"├─ Min membership: {min_membership}")
        logger.info(f"└─ Search: {search_query if search_query else 'None'}")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        # 경로 설정
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']
        counts_dir = workbench_schema['quanti']['counts']

        # source_type에 따라 출력 디렉토리 결정
        if source_type == "deg":
            p_value = float(p_value) if p_value else 0.05
            fold_change = float(fold_change) if fold_change else 2.0
            output_dirname = f"mfuzz_deg_P{p_value}_C{fold_change}_c{cluster_count}_m{m_value if m_value else 'auto'}_mem{min_membership}"
            output_dir = os.path.join(deg_dir, 'edgeR', output_dirname)
        elif source_type == "variance":
            top_n_genes = int(top_n_genes) if top_n_genes else 8000
            output_dirname = f"mfuzz_variance_top{top_n_genes}_c{cluster_count}_m{m_value if m_value else 'auto'}_mem{min_membership}"
            output_dir = os.path.join(counts_dir, output_dirname)
        elif source_type == "tmm":
            output_dirname = f"mfuzz_tmm_full_c{cluster_count}_m{m_value if m_value else 'auto'}_mem{min_membership}"
            output_dir = os.path.join(counts_dir, output_dirname)
        else:
            return jsonify({'error': f'Invalid source_type: {source_type}'}), 400

        logger.info(f"📂 [MFUZZ] Checking directory: {output_dir}")

        if not os.path.exists(output_dir):
            logger.debug(f"ℹ️ [MFUZZ] No cached results found")
            return jsonify({"exists": False, "clusters": [], "total": 0}), 200

        # 클러스터 파일 수집 (cluster_N.tsv 형식만, centroids 제외)
        cluster_files = sorted(glob.glob(os.path.join(output_dir, "cluster_*.tsv")))

        # 검색어가 있을 경우 gene_annotations 로드
        gene_annotations = {}
        if search_query:
            try:
                gene_annotations = load_gene_annotations()
            except Exception as e:
                logger.warning(f"⚠️ [MFUZZ] Failed to load gene annotations: {e}")
                gene_annotations = {}

        clusters = []
        for file_path in cluster_files:
            filename = os.path.basename(file_path)
            # cluster_N.tsv 형식만 처리 (cluster_centroids.tsv 제외)
            try:
                cluster_num = int(filename.split('_')[1].split('.')[0])
            except ValueError:
                # 숫자가 아니면 건너뛰기 (예: cluster_centroids.tsv)
                continue

            # 검색어가 있을 경우 클러스터 내 유전자 검색
            if search_query:
                import re
                search_terms = [term.strip().upper() for term in re.split(r'[,\s\t\n]+', search_query) if term.strip()]
                cluster_contains_search = False

                try:
                    df = pd.read_csv(file_path, sep='\t', encoding='utf-8')
                    if len(df) > 0:
                        gene_id_col = df.columns[0]

                        # 1. gene_id 부분 일치 검색
                        for term in search_terms:
                            if df[gene_id_col].str.upper().str.contains(term, regex=False, na=False).any():
                                cluster_contains_search = True
                                break

                        # 2. gene_symbol 부분 일치 검색
                        if not cluster_contains_search and gene_annotations:
                            for gene_id in df[gene_id_col]:
                                gene_info = gene_annotations.get(gene_id, {})
                                symbol = gene_info.get('symbol', '').upper()
                                if any(term in symbol for term in search_terms):
                                    cluster_contains_search = True
                                    break

                except Exception as e:
                    logger.warning(f"⚠️ [MFUZZ] Failed to search in cluster {cluster_num}: {e}")
                    continue

                if not cluster_contains_search:
                    continue

            with open(file_path, 'r', encoding='utf-8') as f:
                gene_count = sum(1 for line in f) - 1

            clusters.append({
                "id": cluster_num,
                "gene_count": gene_count,
                "file_name": filename
            })

        # ID로 정렬
        clusters.sort(key=lambda x: x['id'])

        logger.info(f"✅ [MFUZZ] Found {len(clusters)} cached clusters{' (search: ' + search_query + ')' if search_query else ''}")

        # 파라미터 구성
        parameters = {
            "source_type": source_type,
            "cluster_count": cluster_count,
            "m_value": m_value,
            "min_membership": min_membership
        }
        if source_type == 'deg':
            parameters['p_value'] = p_value
            parameters['fold_change'] = fold_change
        elif source_type == 'variance':
            parameters['top_n_genes'] = top_n_genes

        return jsonify({
            "exists": True,
            "clusters": clusters,
            "total": len(clusters),
            "parameters": parameters,
            "is_search_result": bool(search_query),
            "search_query": search_query
        }), 200

    except Exception as e:
        logger.exception(f"❌ [MFUZZ] Get clusters failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/mfuzz/previews', methods=['GET'])
def get_mfuzz_cluster_previews(workbench_id: int):
    """
    Get lightweight pattern previews for multiple Mfuzz clusters in one request.
    """
    try:
        source_type = request.args.get('source_type', 'deg')
        p_value = request.args.get('p_value')
        fold_change = request.args.get('fold_change')
        top_n_genes = request.args.get('top_n_genes')
        cluster_count = int(request.args.get('cluster_count', 6))
        m_value_param = request.args.get('m_value', 'auto')
        m_value = None if m_value_param == 'auto' else float(m_value_param)
        min_membership = float(request.args.get('min_membership', 0.5))
        cluster_ids_raw = request.args.get('cluster_ids', '').strip()

        if not cluster_ids_raw:
            return jsonify({'error': 'cluster_ids is required'}), 400

        try:
            cluster_ids = [int(cluster_id.strip()) for cluster_id in cluster_ids_raw.split(',') if cluster_id.strip()]
        except ValueError:
            return jsonify({'error': 'cluster_ids must be integers'}), 400

        # Workbench lookup
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        # Resolve output directory from source_type and params
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']
        counts_dir = workbench_schema['quanti']['counts']

        if source_type == "deg":
            p_value = float(p_value) if p_value else 0.05
            fold_change = float(fold_change) if fold_change else 2.0
            output_dirname = f"mfuzz_deg_P{p_value}_C{fold_change}_c{cluster_count}_m{m_value if m_value else 'auto'}_mem{min_membership}"
            output_dir = os.path.join(deg_dir, 'edgeR', output_dirname)
        elif source_type == "variance":
            top_n_genes = int(top_n_genes) if top_n_genes else 8000
            output_dirname = f"mfuzz_variance_top{top_n_genes}_c{cluster_count}_m{m_value if m_value else 'auto'}_mem{min_membership}"
            output_dir = os.path.join(counts_dir, output_dirname)
        elif source_type == "tmm":
            output_dirname = f"mfuzz_tmm_full_c{cluster_count}_m{m_value if m_value else 'auto'}_mem{min_membership}"
            output_dir = os.path.join(counts_dir, output_dirname)
        else:
            return jsonify({'error': f'Invalid source_type: {source_type}'}), 400

        if not os.path.exists(output_dir):
            return jsonify({"exists": False, "previews": [], "total": 0}), 200

        previews = []
        for cluster_id in cluster_ids:
            file_path = os.path.join(output_dir, f"cluster_{cluster_id}.tsv")
            if not os.path.exists(file_path):
                continue

            preview = parse_mfuzz_cluster_preview(file_path)
            preview = reorder_preview_by_samples_file(workbench_schema, preview)

            previews.append({
                "id": cluster_id,
                "gene_count": preview['gene_count'],
                "samples": preview['samples'],
                "statistics": preview['statistics']
            })

        return jsonify({
            "exists": True,
            "previews": previews,
            "total": len(previews)
        }), 200
    except Exception as e:
        logger.exception(f"❌ [MFUZZ] Get cluster previews failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/mfuzz/cluster/<int:cluster_id>', methods=['GET'])
def get_mfuzz_cluster_data(workbench_id: int, cluster_id: int):
    """
    Mfuzz 특정 클러스터 데이터 조회

    Query Parameters:
        source_type: deg | variance | tmm (required)
        p_value, fold_change: for deg only
        top_n_genes: for variance only
        cluster_count, m_value, min_membership
        search: 검색어 (부분 일치, 대소문자 구분 없음)
        page: 페이지 번호 (default: 1)
        limit: 페이지당 항목 수 (default: 500)

    Response:
        {
            "cluster_id": 1,
            "total_genes": 150,
            "showing_genes": 100,
            "current_page": 1,
            "total_pages": 2,
            "page_size": 100,
            "genes": [
                {
                    "gene_id": "TRINITY_DN1000_c0_g1",
                    "gene_symbol": "NAC001",
                    "membership": 0.95,
                    "sample1": 5.2,
                    "sample2": 6.1,
                    ...
                }
            ],
            "samples": ["sample1", "sample2", ...],
            "is_search_result": false,
            "search_query": ""
        }
    """
    try:
        source_type = request.args.get('source_type', 'deg')
        p_value = request.args.get('p_value')
        fold_change = request.args.get('fold_change')
        top_n_genes = request.args.get('top_n_genes')
        cluster_count = int(request.args.get('cluster_count', 6))
        m_value_param = request.args.get('m_value', 'auto')
        m_value = None if m_value_param == 'auto' else float(m_value_param)
        min_membership = float(request.args.get('min_membership', 0.5))

        # 검색 및 페이지네이션 파라미터
        search_query = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 500))

        logger.info(f"📊 [MFUZZ] Get cluster {cluster_id} (WB:{workbench_id}, source:{source_type}, page:{page}, search:{'yes' if search_query else 'no'})")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        # 경로 설정
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']
        counts_dir = workbench_schema['quanti']['counts']

        # source_type에 따라 출력 디렉토리 결정
        if source_type == "deg":
            p_value = float(p_value) if p_value else 0.05
            fold_change = float(fold_change) if fold_change else 2.0
            output_dirname = f"mfuzz_deg_P{p_value}_C{fold_change}_c{cluster_count}_m{m_value if m_value else 'auto'}_mem{min_membership}"
            output_dir = os.path.join(deg_dir, 'edgeR', output_dirname)
        elif source_type == "variance":
            top_n_genes = int(top_n_genes) if top_n_genes else 8000
            output_dirname = f"mfuzz_variance_top{top_n_genes}_c{cluster_count}_m{m_value if m_value else 'auto'}_mem{min_membership}"
            output_dir = os.path.join(counts_dir, output_dirname)
        elif source_type == "tmm":
            output_dirname = f"mfuzz_tmm_full_c{cluster_count}_m{m_value if m_value else 'auto'}_mem{min_membership}"
            output_dir = os.path.join(counts_dir, output_dirname)
        else:
            return jsonify({'error': f'Invalid source_type: {source_type}'}), 400

        file_path = os.path.join(output_dir, f"cluster_{cluster_id}.tsv")

        if not os.path.exists(file_path):
            logger.error(f"❌ [MFUZZ] Cluster file not found: {file_path}")
            return jsonify({"error": "Cluster file not found"}), 404

        # 파싱
        df = pd.read_csv(file_path, sep='\t')

        # Gene annotations 추가
        gene_annotations = load_gene_annotations()

        # 전체 유전자 수
        total_genes = len(df)

        # 검색 필터 적용
        if search_query:
            # 검색어를 쉼표, 공백, 탭, 줄바꿈으로 분리
            import re
            search_terms = [term.strip().upper() for term in re.split(r'[,\s\t\n]+', search_query) if term.strip()]

            if search_terms:
                # 1. gene_id로 부분 일치 검색 (대소문자 구분 없이)
                mask = pd.Series([False] * len(df), index=df.index)
                for term in search_terms:
                    term_mask = df['gene_id'].str.upper().str.contains(term, regex=False, na=False)
                    mask |= term_mask

                # 2. gene_symbol로 부분 일치 검색
                gene_ids_from_symbols = []
                for gene_id, info in gene_annotations.items():
                    symbol = info.get('symbol', '')
                    symbol_upper = symbol.upper()
                    if any(term in symbol_upper for term in search_terms):
                        gene_ids_from_symbols.append(gene_id)

                # gene_symbol로 찾은 gene_id를 마스크에 추가
                if gene_ids_from_symbols:
                    mask |= df['gene_id'].isin(gene_ids_from_symbols)

                # 필터링 적용
                df = df[mask]

        # 총 검색 결과 수
        filtered_total = len(df)

        # 페이지네이션 적용
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        df_page = df.iloc[start_idx:end_idx]

        # 응답 데이터 생성
        genes_data = []
        for _, row in df_page.iterrows():
            gene_info = gene_annotations.get(row['gene_id'], {})
            gene_dict = {
                "gene_id": row['gene_id'],
                "gene_symbol": gene_info.get('symbol', row['gene_id']),
                "gene_description": gene_info.get('description', 'No description available'),
                "membership": float(row['membership'])
            }
            # 샘플 값 추가 (gene_id, membership 제외)
            for col in df.columns:
                if col not in ['gene_id', 'membership']:
                    gene_dict[col] = float(row[col]) if pd.notna(row[col]) else 0.0

            genes_data.append(gene_dict)

        samples = [col for col in df.columns if col not in ['gene_id', 'membership']]

        # 총 페이지 수 계산
        total_pages = (filtered_total + limit - 1) // limit if filtered_total > 0 else 1

        response = {
            'cluster_id': cluster_id,
            'total_genes': filtered_total,
            'gene_count': filtered_total,  # 하위 호환성을 위해 유지
            'showing_genes': len(genes_data),
            'current_page': page,
            'total_pages': total_pages,
            'page_size': limit,
            'genes': genes_data,
            'samples': samples,
            'is_search_result': bool(search_query),
            'search_query': search_query
        }

        logger.info(f"✅ [MFUZZ] Returned {len(genes_data)} genes (page {page}/{total_pages})")

        return jsonify(response), 200

    except Exception as e:
        logger.exception(f"❌ [MFUZZ] Get cluster data failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/mfuzz/download/<int:cluster_id>', methods=['GET'])
def download_mfuzz_cluster(workbench_id: int, cluster_id: int):
    """
    Mfuzz 클러스터 데이터 다운로드

    Query Parameters:
        p_value, fold_change, cluster_count, m_value, min_membership

    Response:
        TSV 파일 다운로드
    """
    try:
        p_value = float(request.args.get('p_value', 0.1))
        fold_change = float(request.args.get('fold_change', 1.0))
        cluster_count = int(request.args.get('cluster_count', 6))
        m_value_param = request.args.get('m_value', 'auto')
        m_value = None if m_value_param == 'auto' else float(m_value_param)
        min_membership = float(request.args.get('min_membership', 0.5))

        logger.info(f"📥 [MFUZZ] Download cluster:")
        logger.info(f"├─ Workbench ID: {workbench_id}")
        logger.info(f"└─ Cluster ID: {cluster_id}")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        # 파일 경로
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']

        matrix_name = f"diffExpr.P{p_value}_C{fold_change}.matrix.RData"
        output_dirname = f"mfuzz_c{cluster_count}_m{m_value if m_value else 'auto'}_mem{min_membership}"
        output_dir = os.path.join(deg_dir, 'edgeR', f"{matrix_name}.{output_dirname}")
        file_path = os.path.join(output_dir, f"cluster_{cluster_id}.tsv")

        if not os.path.exists(file_path):
            logger.error(f"❌ [MFUZZ] File not found: {file_path}")
            return jsonify({"error": "File not found"}), 404

        logger.info(f"✅ [MFUZZ] Sending file: mfuzz_cluster_{cluster_id}.tsv")

        return send_file(
            file_path,
            as_attachment=True,
            download_name=f"mfuzz_cluster_{cluster_id}.tsv",
            mimetype='text/tab-separated-values'
        )

    except Exception as e:
        logger.exception(f"❌ [MFUZZ] Download failed")
        return jsonify({'error': str(e)}), 500


# ========================================
# WGCNA Clustering
# ========================================

def parse_wgcna_module_preview(file_path: str) -> dict:
    """
    Parse WGCNA module TSV for lightweight preview statistics only.
    """
    try:
        df = pd.read_csv(file_path, sep='\t', encoding='utf-8')
        # WGCNA module file format: gene_id, module_membership, sample1, sample2, ...
        sample_cols = list(df.columns[2:]) if len(df.columns) > 2 else []
        numeric_df = df[sample_cols].apply(pd.to_numeric, errors='coerce').fillna(0.0)
        return {
            "gene_count": len(df.index),
            "samples": sample_cols,
            "statistics": {
                "mean": numeric_df.mean(axis=0).tolist(),
                "median": numeric_df.median(axis=0).tolist()
            }
        }
    except Exception:
        logger.exception(f"❌ [WGCNA] Error parsing preview module file: {file_path}")
        raise


def run_wgcna_clustering_docker(workbench_id: int, source_type: str,
                                 p_value: float = None, fold_change: float = None,
                                 top_n_genes: int = 5000,
                                 soft_power: str = "auto",
                                 min_module_size: int = 30,
                                 deep_split: int = 2,
                                 merge_cut_height: float = 0.25):
    """
    WGCNA (Weighted Gene Co-expression Network Analysis) Docker 실행

    Args:
        workbench_id: 워크벤치 ID
        source_type: 'deg' | 'variance' | 'tmm'
        p_value: P-value cutoff (source_type='deg'인 경우)
        fold_change: Fold change cutoff (source_type='deg'인 경우)
        top_n_genes: Top N genes by MAD (source_type='variance'인 경우, default: 5000)
        soft_power: Soft thresholding power ('auto' or number, default: 'auto')
        min_module_size: Minimum module size (default: 30)
        deep_split: Deep split parameter 0-4 (default: 2)
        merge_cut_height: Module merge cut height (default: 0.25)

    Returns:
        dict: {
            "success": bool,
            "modules": list,
            "total": int,
            "output_dir": str,
            "parameters": dict,
            "error": str (실패 시)
        }
    """
    try:
        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return {
                "success": False,
                "error": "Workbench not found"
            }

        # 경로 설정
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        workbench_dir = workbench_schema['base']
        deg_dir = workbench_schema['deg']
        counts_dir = workbench_schema['quanti']['counts']

        # 스크립트 디렉토리 생성 및 복사
        script_dir = os.path.join(workbench_dir, 'script')
        os.makedirs(script_dir, exist_ok=True)

        # R 스크립트 복사 (VizR 컨테이너 → 워크벤치)
        import shutil
        source_script = os.path.join(os.path.dirname(__file__), '..', 'pipeline', 'scripts', 'run_wgcna.R')
        dest_script = os.path.join(script_dir, 'run_wgcna.R')

        # 스크립트가 존재하는지 확인
        if not os.path.exists(source_script):
            logger.error(f"❌ [WGCNA] R script not found: {source_script}")
            return {
                "success": False,
                "error": "WGCNA R script not found. Please ensure run_wgcna.R exists in backend/pipeline/scripts/"
            }

        shutil.copy2(source_script, dest_script)
        logger.info(f"📋 [WGCNA] R script copied: {dest_script}")

        # source_type에 따라 분기
        if source_type == "deg":
            # ========== Option 1: DEG-filtered ==========
            matrix_name = f"diffExpr.P{p_value}_C{fold_change}.matrix.RData"
            matrix_path = os.path.join(deg_dir, 'edgeR', matrix_name)

            # Matrix 파일 존재 확인 및 자동 생성
            if not os.path.exists(matrix_path):
                logger.info(f"📁 [WGCNA] DEG matrix not found, generating: {matrix_name}")

                # run_dea() 호출하여 파일 생성
                from backend.pipeline.utils.de_analysis import run_dea

                # TMM matrix 경로
                tmm_matrix_file = os.path.join(counts_dir, 'genes.TMM.matrix')

                # samples.txt 경로
                samples_dir = workbench_schema['quanti']['samples']
                samples_file = os.path.join(samples_dir, 'samples.txt')

                # 파일 존재 확인
                if not os.path.exists(tmm_matrix_file):
                    logger.error(f"❌ [WGCNA] TMM matrix not found: {tmm_matrix_file}")
                    return {
                        "success": False,
                        "error": "TMM matrix file not found. Please run quantification first."
                    }

                if not os.path.exists(samples_file):
                    logger.error(f"❌ [WGCNA] Samples file not found: {samples_file}")
                    return {
                        "success": False,
                        "error": "Samples file not found. Please run quantification first."
                    }

                # run_dea() 호출
                edger_dir = os.path.join(deg_dir, 'edgeR')
                dea_result = run_dea(
                    workbench_root=workbench_dir,
                    output_dir=edger_dir,
                    tmm_matrix_file=tmm_matrix_file,
                    samples_file=samples_file,
                    workbench_id=workbench_id,
                    worker_id="wgcna_worker",
                    p_value=p_value,
                    fold_change=fold_change
                )

                if not dea_result.get('success', False):
                    error_msg = dea_result.get('error', 'Unknown error')
                    logger.error(f"❌ [WGCNA] Failed to generate DEG matrix: {error_msg}")
                    return {
                        "success": False,
                        "error": f"Failed to generate DEG matrix: {error_msg}"
                    }

                logger.info(f"✅ [WGCNA] DEG matrix generated successfully: {matrix_name}")
            else:
                logger.info(f"✅ [WGCNA] Using existing DEG matrix: {matrix_name}")

            # 출력 디렉토리 설정
            output_dirname = f"wgcna_deg_P{p_value}_C{fold_change}_sp{soft_power}_ms{min_module_size}_ds{deep_split}_mc{merge_cut_height}"
            output_dir = os.path.join(deg_dir, 'edgeR', output_dirname)
            os.makedirs(output_dir, exist_ok=True)

            # WGCNA 명령어 구성
            wgcna_command = (
                f"Rscript /data/script/run_wgcna.R "
                f"--source-type deg "
                f"--matrix /data/deg/edgeR/{matrix_name} "
                f"--soft-power {soft_power} "
                f"--min-module-size {min_module_size} "
                f"--deep-split {deep_split} "
                f"--merge-cut-height {merge_cut_height} "
                f"--output /data/deg/edgeR/{output_dirname}"
            )

        elif source_type == "variance":
            # ========== Option 2: Variance-filtered (recommended) ==========
            tmm_matrix_path = os.path.join(counts_dir, 'genes.TMM.matrix')

            # TMM matrix 파일 존재 확인
            if not os.path.exists(tmm_matrix_path):
                logger.error(f"❌ [WGCNA] TMM matrix not found: {tmm_matrix_path}")
                return {
                    "success": False,
                    "error": "TMM matrix not found. Please run quantification first."
                }

            # 출력 디렉토리 설정
            output_dirname = f"wgcna_variance_top{top_n_genes}_sp{soft_power}_ms{min_module_size}_ds{deep_split}_mc{merge_cut_height}"
            output_dir = os.path.join(counts_dir, output_dirname)
            os.makedirs(output_dir, exist_ok=True)

            # WGCNA 명령어 구성
            wgcna_command = (
                f"Rscript /data/script/run_wgcna.R "
                f"--source-type variance "
                f"--tmm-matrix /data/quanti/counts/genes.TMM.matrix "
                f"--top-n-genes {top_n_genes} "
                f"--soft-power {soft_power} "
                f"--min-module-size {min_module_size} "
                f"--deep-split {deep_split} "
                f"--merge-cut-height {merge_cut_height} "
                f"--output /data/quanti/counts/{output_dirname}"
            )

        elif source_type == "tmm":
            # ========== Option 3: Full TMM (not recommended) ==========
            tmm_matrix_path = os.path.join(counts_dir, 'genes.TMM.matrix')

            # TMM matrix 파일 존재 확인
            if not os.path.exists(tmm_matrix_path):
                logger.error(f"❌ [WGCNA] TMM matrix not found: {tmm_matrix_path}")
                return {
                    "success": False,
                    "error": "TMM matrix not found. Please run quantification first."
                }

            # 출력 디렉토리 설정
            output_dirname = f"wgcna_tmm_full_sp{soft_power}_ms{min_module_size}_ds{deep_split}_mc{merge_cut_height}"
            output_dir = os.path.join(counts_dir, output_dirname)
            os.makedirs(output_dir, exist_ok=True)

            # WGCNA 명령어 구성
            wgcna_command = (
                f"Rscript /data/script/run_wgcna.R "
                f"--source-type tmm "
                f"--tmm-matrix /data/quanti/counts/genes.TMM.matrix "
                f"--soft-power {soft_power} "
                f"--min-module-size {min_module_size} "
                f"--deep-split {deep_split} "
                f"--merge-cut-height {merge_cut_height} "
                f"--output /data/quanti/counts/{output_dirname}"
            )

        else:
            return {
                "success": False,
                "error": f"Invalid source_type: {source_type}. Must be 'deg', 'variance', or 'tmm'."
            }

        # 호스트 경로로 변환
        host_workbench_dir = workbench_dir.replace(SharedConfig.VIZR_PATH, SharedConfig.HOST_VIZR_PATH)
        logger.info(f"🔄 [WGCNA] Path conversion: container→host")
        logger.info(f"   ├─ Container: {workbench_dir}")
        logger.info(f"   └─ Host: {host_workbench_dir}")

        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_workbench_dir}:/data",
            "-w", "/data",
            SharedConfig.TRINITY_IMAGE,
            "bash", "-c",
            wgcna_command
        ]

        # 실행
        logger.info(f"🚀 [WGCNA] Running WGCNA clustering:")
        logger.info(f"├─ Workbench: {workbench['name']} (ID: {workbench_id})")
        logger.info(f"├─ Source type: {source_type}")
        if source_type == "deg":
            logger.info(f"├─ P-value: {p_value}")
            logger.info(f"├─ Fold Change: {fold_change}")
        elif source_type == "variance":
            logger.info(f"├─ Top N genes: {top_n_genes}")
        logger.info(f"├─ Soft power: {soft_power}")
        logger.info(f"├─ Min module size: {min_module_size}")
        logger.info(f"├─ Deep split: {deep_split}")
        logger.info(f"├─ Merge cut height: {merge_cut_height}")

        import shlex
        cmd_display = ' '.join(shlex.quote(arg) for arg in docker_cmd)
        logger.info(f"└─ Command: {cmd_display}")

        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=900  # 15분 타임아웃 (WGCNA는 Mfuzz보다 오래 걸릴 수 있음)
        )

        if result.returncode != 0:
            logger.error(f"❌ [WGCNA] Docker execution failed:")
            logger.error(f"   └─ stderr: {result.stderr}")
            return {
                "success": False,
                "error": f"WGCNA clustering failed: {result.stderr}"
            }

        logger.info(f"✅ [WGCNA] Docker execution completed")

        # 결과 수집
        if not os.path.exists(output_dir):
            logger.error(f"❌ [WGCNA] Output directory not created: {output_dir}")
            return {
                "success": False,
                "error": "WGCNA output directory not found"
            }

        # modules 서브디렉토리에서 모듈 파일 조회
        modules_dir = os.path.join(output_dir, "modules")
        if not os.path.exists(modules_dir):
            logger.error(f"❌ [WGCNA] Modules directory not found: {modules_dir}")
            return {
                "success": False,
                "error": "WGCNA modules directory not found"
            }

        module_files = sorted(glob.glob(os.path.join(modules_dir, "*.tsv")))

        # 모듈 메타데이터 생성
        modules = []
        for file_path in module_files:
            filename = os.path.basename(file_path)
            # <color>.tsv 형식에서 색상 추출
            module_color = filename.replace(".tsv", "")

            # grey 모듈은 제외 (할당되지 않은 유전자들)
            if module_color.lower() == "grey":
                continue

            # 유전자 수 계산 (헤더 제외)
            with open(file_path, 'r', encoding='utf-8') as f:
                gene_count = sum(1 for line in f) - 1

            modules.append({
                "id": module_color,
                "gene_count": gene_count,
                "file_name": filename
            })

        if not modules:
            logger.warning(f"⚠️ [WGCNA] No module files generated")
            return {
                "success": False,
                "error": "No modules generated. Try adjusting min_module_size or other parameters."
            }

        # 모듈 크기 순으로 정렬 (큰 것부터)
        modules.sort(key=lambda x: x['gene_count'], reverse=True)

        logger.info(f"✅ [WGCNA] Generated {len(modules)} modules:")
        for module in modules:
            logger.info(f"   ├─ Module {module['id']}: {module['gene_count']} genes")

        return {
            "success": True,
            "modules": modules,
            "total": len(modules),
            "output_dir": output_dir,
            "parameters": {
                "source_type": source_type,
                "soft_power": soft_power,
                "min_module_size": min_module_size,
                "deep_split": deep_split,
                "merge_cut_height": merge_cut_height,
                "p_value": p_value if source_type == "deg" else None,
                "fold_change": fold_change if source_type == "deg" else None,
                "top_n_genes": top_n_genes if source_type == "variance" else None
            }
        }

    except subprocess.TimeoutExpired:
        logger.error(f"❌ [WGCNA] Execution timeout (>15 minutes)")
        return {
            "success": False,
            "error": "WGCNA clustering timeout (>15 minutes)"
        }
    except Exception as e:
        logger.exception(f"❌ [WGCNA] Unexpected error")
        return {
            "success": False,
            "error": str(e)
        }


@clustering_bp.route('/<int:workbench_id>/clustering/wgcna/run', methods=['POST'])
def run_wgcna(workbench_id: int):
    """
    WGCNA 클러스터링 실행

    Request Body:
        {
            "source_type": "variance",      # deg|variance|tmm
            "p_value": 0.05,                # source_type='deg'인 경우
            "fold_change": 2.0,             # source_type='deg'인 경우
            "top_n_genes": 5000,            # source_type='variance'인 경우
            "soft_power": "auto",           # auto 또는 숫자
            "min_module_size": 30,
            "deep_split": 2,
            "merge_cut_height": 0.25
        }

    Response:
        {
            "success": true,
            "modules": [
                {"id": "turquoise", "gene_count": 500, "file_name": "module_turquoise.tsv"},
                {"id": "blue", "gene_count": 350, "file_name": "module_blue.tsv"},
                ...
            ],
            "total": 8,
            "output_dir": "...",
            "parameters": {...}
        }
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        source_type = data.get('source_type', 'variance')
        p_value = data.get('p_value')
        fold_change = data.get('fold_change')
        top_n_genes = int(data.get('top_n_genes', 5000))
        soft_power = data.get('soft_power', 'auto')
        min_module_size = int(data.get('min_module_size', 30))
        deep_split = int(data.get('deep_split', 2))
        merge_cut_height = float(data.get('merge_cut_height', 0.25))

        # Convert to appropriate types
        if p_value is not None:
            p_value = float(p_value)
        if fold_change is not None:
            fold_change = float(fold_change)

        # soft_power는 'auto' 문자열 또는 숫자
        if soft_power != 'auto':
            try:
                soft_power = int(soft_power)
            except (ValueError, TypeError):
                soft_power = 'auto'

        logger.info(f"📊 [WGCNA] Run request:")
        logger.info(f"├─ Workbench ID: {workbench_id}")
        logger.info(f"├─ Source type: {source_type}")
        if source_type == "deg":
            logger.info(f"├─ P-value: {p_value}")
            logger.info(f"├─ Fold change: {fold_change}")
        elif source_type == "variance":
            logger.info(f"├─ Top N genes: {top_n_genes}")
        logger.info(f"├─ Soft power: {soft_power}")
        logger.info(f"├─ Min module size: {min_module_size}")
        logger.info(f"├─ Deep split: {deep_split}")
        logger.info(f"└─ Merge cut height: {merge_cut_height}")

        # WGCNA 실행
        result = run_wgcna_clustering_docker(
            workbench_id=workbench_id,
            source_type=source_type,
            p_value=p_value,
            fold_change=fold_change,
            top_n_genes=top_n_genes,
            soft_power=soft_power,
            min_module_size=min_module_size,
            deep_split=deep_split,
            merge_cut_height=merge_cut_height
        )

        if result['success']:
            logger.info(f"✅ [WGCNA] Successfully generated {result['total']} modules")
            return jsonify(result), 200
        else:
            logger.error(f"❌ [WGCNA] Failed: {result.get('error')}")
            return jsonify(result), 500

    except Exception as e:
        logger.exception(f"❌ [WGCNA] Run endpoint failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/wgcna/modules', methods=['GET'])
def get_wgcna_modules(workbench_id: int):
    """
    WGCNA 모듈 목록 조회 (캐시된 결과)

    Query Parameters:
        source_type: deg | variance | tmm (required)
        p_value: P-value cutoff (for deg only)
        fold_change: Fold change cutoff (for deg only)
        top_n_genes: Top N genes (for variance only)
        soft_power: Soft power (default: auto)
        min_module_size: Min module size (default: 30)
        deep_split: Deep split (default: 2)
        merge_cut_height: Merge cut height (default: 0.25)
        search: 검색어 (유전자 ID 또는 Symbol, 부분 일치, 대소문자 구분 없음)

    Response:
        {
            "exists": true,
            "modules": [
                {"id": "turquoise", "gene_count": 500, "file_name": "module_turquoise.tsv"},
                ...
            ],
            "total": 8,
            "parameters": {...},
            "is_search_result": false,
            "search_query": ""
        }
    """
    try:
        source_type = request.args.get('source_type', 'variance')
        p_value = request.args.get('p_value')
        fold_change = request.args.get('fold_change')
        top_n_genes = request.args.get('top_n_genes')
        soft_power = request.args.get('soft_power', 'auto')
        min_module_size = int(request.args.get('min_module_size', 30))
        deep_split = int(request.args.get('deep_split', 2))
        merge_cut_height = float(request.args.get('merge_cut_height', 0.25))
        search_query = request.args.get('search', '').strip()

        # Convert parameters
        if p_value:
            p_value = float(p_value)
        if fold_change:
            fold_change = float(fold_change)
        if top_n_genes:
            top_n_genes = int(top_n_genes)
        else:
            top_n_genes = 5000

        logger.debug(f"🔍 [WGCNA] Get modules request:")
        logger.debug(f"├─ Workbench ID: {workbench_id}")
        logger.debug(f"├─ Source type: {source_type}")
        logger.debug(f"├─ Soft power: {soft_power}")
        logger.debug(f"└─ Min module size: {min_module_size}")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        # 경로 설정
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']
        counts_dir = workbench_schema['quanti']['counts']

        # 출력 디렉토리 결정
        if source_type == "deg":
            output_dirname = f"wgcna_deg_P{p_value}_C{fold_change}_sp{soft_power}_ms{min_module_size}_ds{deep_split}_mc{merge_cut_height}"
            output_dir = os.path.join(deg_dir, 'edgeR', output_dirname)
        elif source_type == "variance":
            output_dirname = f"wgcna_variance_top{top_n_genes}_sp{soft_power}_ms{min_module_size}_ds{deep_split}_mc{merge_cut_height}"
            output_dir = os.path.join(counts_dir, output_dirname)
        elif source_type == "tmm":
            output_dirname = f"wgcna_tmm_full_sp{soft_power}_ms{min_module_size}_ds{deep_split}_mc{merge_cut_height}"
            output_dir = os.path.join(counts_dir, output_dirname)
        else:
            return jsonify({'error': f'Invalid source_type: {source_type}'}), 400

        # 디렉토리 존재 여부 확인
        if not os.path.exists(output_dir):
            logger.debug(f"⚠️ [WGCNA] Output directory not found: {output_dir}")
            return jsonify({
                'exists': False,
                'modules': [],
                'total': 0,
                'parameters': {
                    'source_type': source_type,
                    'soft_power': soft_power,
                    'min_module_size': min_module_size,
                    'deep_split': deep_split,
                    'merge_cut_height': merge_cut_height
                }
            }), 200

        # 모듈 파일 조회 (modules 서브디렉토리에서)
        modules_dir = os.path.join(output_dir, "modules")
        module_files = sorted(glob.glob(os.path.join(modules_dir, "*.tsv")))

        # 검색어가 있을 경우 gene_annotations 로드
        gene_annotations = {}
        if search_query:
            try:
                gene_annotations = load_gene_annotations()
            except Exception as e:
                logger.warning(f"⚠️ [WGCNA] Failed to load gene annotations: {e}")
                gene_annotations = {}

        modules = []
        for file_path in module_files:
            filename = os.path.basename(file_path)
            module_color = filename.replace(".tsv", "")  # blue.tsv -> blue

            # grey 모듈은 제외 (WGCNA에서 grey는 미할당 유전자)
            if module_color.lower() == "grey":
                continue

            # 검색어가 있을 경우 모듈 내 유전자 검색
            if search_query:
                import re
                search_terms = [term.strip().upper() for term in re.split(r'[,\s\t\n]+', search_query) if term.strip()]
                module_contains_search = False

                try:
                    df = pd.read_csv(file_path, sep='\t', encoding='utf-8')
                    if len(df) > 0:
                        gene_id_col = df.columns[0]

                        # 1. gene_id 부분 일치 검색
                        for term in search_terms:
                            if df[gene_id_col].str.upper().str.contains(term, regex=False, na=False).any():
                                module_contains_search = True
                                break

                        # 2. gene_symbol 부분 일치 검색
                        if not module_contains_search and gene_annotations:
                            for gene_id in df[gene_id_col]:
                                gene_info = gene_annotations.get(gene_id, {})
                                symbol = gene_info.get('symbol', '').upper()
                                if any(term in symbol for term in search_terms):
                                    module_contains_search = True
                                    break

                except Exception as e:
                    logger.warning(f"⚠️ [WGCNA] Failed to search in module {module_color}: {e}")
                    continue

                # 검색어가 포함되지 않은 모듈은 제외
                if not module_contains_search:
                    continue

            # 유전자 수 계산
            with open(file_path, 'r', encoding='utf-8') as f:
                gene_count = sum(1 for line in f) - 1  # 헤더 제외

            modules.append({
                "id": module_color,
                "gene_count": gene_count,
                "file_name": filename
            })

        # 모듈 크기 순으로 정렬
        modules.sort(key=lambda x: x['gene_count'], reverse=True)

        exists = len(modules) > 0
        logger.debug(f"✅ [WGCNA] Found {len(modules)} modules")

        return jsonify({
            'exists': exists,
            'modules': modules,
            'total': len(modules),
            'is_search_result': bool(search_query),
            'search_query': search_query,
            'parameters': {
                'source_type': source_type,
                'soft_power': soft_power,
                'min_module_size': min_module_size,
                'deep_split': deep_split,
                'merge_cut_height': merge_cut_height,
                'p_value': p_value if source_type == "deg" else None,
                'fold_change': fold_change if source_type == "deg" else None,
                'top_n_genes': top_n_genes if source_type == "variance" else None
            }
        }), 200

    except Exception as e:
        logger.exception(f"❌ [WGCNA] Get modules failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/wgcna/previews', methods=['GET'])
def get_wgcna_module_previews(workbench_id: int):
    """
    Get lightweight pattern previews for multiple WGCNA modules in one request.
    """
    try:
        source_type = request.args.get('source_type', 'variance')
        p_value = request.args.get('p_value')
        fold_change = request.args.get('fold_change')
        top_n_genes = request.args.get('top_n_genes')
        soft_power = request.args.get('soft_power', 'auto')
        min_module_size = int(request.args.get('min_module_size', 30))
        deep_split = int(request.args.get('deep_split', 2))
        merge_cut_height = float(request.args.get('merge_cut_height', 0.25))
        module_ids_raw = request.args.get('module_ids', '').strip()

        if not module_ids_raw:
            return jsonify({'error': 'module_ids is required'}), 400

        module_ids = [module_id.strip() for module_id in module_ids_raw.split(',') if module_id.strip()]
        if not module_ids:
            return jsonify({'error': 'module_ids is required'}), 400

        if p_value:
            p_value = float(p_value)
        if fold_change:
            fold_change = float(fold_change)
        if top_n_genes:
            top_n_genes = int(top_n_genes)
        else:
            top_n_genes = 5000

        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']
        counts_dir = workbench_schema['quanti']['counts']

        if source_type == "deg":
            output_dirname = f"wgcna_deg_P{p_value}_C{fold_change}_sp{soft_power}_ms{min_module_size}_ds{deep_split}_mc{merge_cut_height}"
            output_dir = os.path.join(deg_dir, 'edgeR', output_dirname)
        elif source_type == "variance":
            output_dirname = f"wgcna_variance_top{top_n_genes}_sp{soft_power}_ms{min_module_size}_ds{deep_split}_mc{merge_cut_height}"
            output_dir = os.path.join(counts_dir, output_dirname)
        elif source_type == "tmm":
            output_dirname = f"wgcna_tmm_full_sp{soft_power}_ms{min_module_size}_ds{deep_split}_mc{merge_cut_height}"
            output_dir = os.path.join(counts_dir, output_dirname)
        else:
            return jsonify({'error': f'Invalid source_type: {source_type}'}), 400

        modules_dir = os.path.join(output_dir, "modules")
        if not os.path.exists(modules_dir):
            return jsonify({"exists": False, "previews": [], "total": 0}), 200

        previews = []
        for module_id in module_ids:
            file_path = os.path.join(modules_dir, f"{module_id}.tsv")
            if not os.path.exists(file_path):
                continue

            preview = parse_wgcna_module_preview(file_path)
            preview = reorder_preview_by_samples_file(workbench_schema, preview)
            previews.append({
                "id": module_id,
                "gene_count": preview["gene_count"],
                "samples": preview["samples"],
                "statistics": preview["statistics"]
            })

        return jsonify({
            "exists": True,
            "previews": previews,
            "total": len(previews)
        }), 200
    except Exception as e:
        logger.exception(f"❌ [WGCNA] Get module previews failed")
        return jsonify({'error': str(e)}), 500


@clustering_bp.route('/<int:workbench_id>/clustering/wgcna/modules/<module_id>', methods=['GET'])
def get_wgcna_module_data(workbench_id: int, module_id: str):
    """
    WGCNA 특정 모듈의 상세 데이터 조회

    Query Parameters:
        source_type: deg | variance | tmm (required)
        p_value, fold_change: for deg only
        top_n_genes: for variance only
        soft_power, min_module_size, deep_split, merge_cut_height
        search: 검색어 (부분 일치, 대소문자 구분 없음)
        page: 페이지 번호 (default: 1)
        limit: 페이지당 항목 수 (default: 500)

    Response:
        {
            "module_id": "turquoise",
            "gene_count": 500,
            "total_genes": 500,
            "showing_genes": 100,
            "current_page": 1,
            "total_pages": 5,
            "page_size": 100,
            "genes": [
                {
                    "gene_id": "TRINITY_DN1000_c0_g1",
                    "gene_symbol": "NAC001",
                    "module_membership": 0.95,
                    "sample1": 5.2,
                    "sample2": 6.1,
                    ...
                }
            ],
            "samples": ["sample1", "sample2", ...],
            "eigengene_values": [0.234, -0.156, 0.891, ...],
            "is_search_result": false,
            "search_query": ""
        }
    """
    try:
        source_type = request.args.get('source_type', 'variance')
        p_value = request.args.get('p_value')
        fold_change = request.args.get('fold_change')
        top_n_genes = request.args.get('top_n_genes')
        soft_power = request.args.get('soft_power', 'auto')
        min_module_size = int(request.args.get('min_module_size', 30))
        deep_split = int(request.args.get('deep_split', 2))
        merge_cut_height = float(request.args.get('merge_cut_height', 0.25))

        # 검색 및 페이지네이션 파라미터
        search_query = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 500))

        # Convert parameters
        if p_value:
            p_value = float(p_value)
        if fold_change:
            fold_change = float(fold_change)
        if top_n_genes:
            top_n_genes = int(top_n_genes)
        else:
            top_n_genes = 5000

        logger.info(f"📊 [WGCNA] Get module {module_id} (WB:{workbench_id}, source:{source_type}, page:{page}, search:{'yes' if search_query else 'no'})")

        # 워크벤치 조회
        with database.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vizr_workbench WHERE id = ?", (workbench_id,))
            workbench = cursor.fetchone()

        if not workbench:
            return jsonify({'error': 'Workbench not found'}), 404

        # 경로 설정
        workbench_schema = get_workbench_schema(workbench['name'], workbench['user_id'])
        deg_dir = workbench_schema['deg']
        counts_dir = workbench_schema['quanti']['counts']

        # 출력 디렉토리 결정
        if source_type == "deg":
            output_dirname = f"wgcna_deg_P{p_value}_C{fold_change}_sp{soft_power}_ms{min_module_size}_ds{deep_split}_mc{merge_cut_height}"
            output_dir = os.path.join(deg_dir, 'edgeR', output_dirname)
        elif source_type == "variance":
            output_dirname = f"wgcna_variance_top{top_n_genes}_sp{soft_power}_ms{min_module_size}_ds{deep_split}_mc{merge_cut_height}"
            output_dir = os.path.join(counts_dir, output_dirname)
        elif source_type == "tmm":
            output_dirname = f"wgcna_tmm_full_sp{soft_power}_ms{min_module_size}_ds{deep_split}_mc{merge_cut_height}"
            output_dir = os.path.join(counts_dir, output_dirname)
        else:
            return jsonify({'error': f'Invalid source_type: {source_type}'}), 400

        # 모듈 파일 경로 (modules 서브디렉토리에서)
        file_path = os.path.join(output_dir, "modules", f"{module_id}.tsv")

        if not os.path.exists(file_path):
            logger.error(f"❌ [WGCNA] Module file not found: {file_path}")
            return jsonify({'error': f'Module {module_id} not found'}), 404

        # 파일 파싱
        df = pd.read_csv(file_path, sep='\t', encoding='utf-8')

        # Gene annotations 추가
        gene_annotations = load_gene_annotations()

        # 전체 유전자 수
        total_genes = len(df)

        # 검색 필터 적용
        if search_query:
            # 검색어를 쉼표, 공백, 탭, 줄바꿈으로 분리
            import re
            search_terms = [term.strip().upper() for term in re.split(r'[,\s\t\n]+', search_query) if term.strip()]

            if search_terms:
                # 첫 번째 컬럼이 gene_id
                gene_id_col = df.columns[0]

                # 1. gene_id로 부분 일치 검색 (대소문자 구분 없이)
                mask = pd.Series([False] * len(df), index=df.index)
                for term in search_terms:
                    term_mask = df[gene_id_col].str.upper().str.contains(term, regex=False, na=False)
                    mask |= term_mask

                # 2. gene_symbol로 부분 일치 검색
                gene_ids_from_symbols = []
                for gene_id, info in gene_annotations.items():
                    symbol = info.get('symbol', '')
                    symbol_upper = symbol.upper()
                    if any(term in symbol_upper for term in search_terms):
                        gene_ids_from_symbols.append(gene_id)

                if gene_ids_from_symbols:
                    symbol_mask = df[gene_id_col].isin(gene_ids_from_symbols)
                    mask |= symbol_mask

                # 필터 적용
                df = df[mask]

        # 필터링 후 총 유전자 수
        filtered_total = len(df)

        # 페이지네이션 적용
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        df_page = df.iloc[start_idx:end_idx]

        # 총 페이지 수 계산
        total_pages = (filtered_total + limit - 1) // limit if filtered_total > 0 else 1

        # 데이터 변환
        genes_data = []
        # 첫 번째 컬럼은 gene_id, 두 번째는 module_membership, 나머지는 샘플 발현값
        for _, row in df_page.iterrows():
            gene_id = row.iloc[0]
            module_membership = float(row.iloc[1]) if pd.notna(row.iloc[1]) else 0.0
            gene_info = gene_annotations.get(gene_id, {})

            gene_dict = {
                "gene_id": gene_id,
                "gene_symbol": gene_info.get('symbol', gene_id),
                "gene_description": gene_info.get('description', 'No description available'),
                "module_membership": module_membership
            }

            # 샘플 발현값 추가 (3번째 컬럼부터)
            for i in range(2, len(row)):
                sample_name = df.columns[i]
                value = float(row.iloc[i]) if pd.notna(row.iloc[i]) else 0.0
                gene_dict[sample_name] = value

            genes_data.append(gene_dict)

        # 샘플 이름 추출 (3번째 컬럼부터)
        samples = df.columns[2:].tolist()

        # Module eigengene 값 읽기
        eigengene_file = os.path.join(output_dir, "module_eigengenes.tsv")
        eigengene_values = []

        if os.path.exists(eigengene_file):
            try:
                # Read eigengene file
                eigengene_df = pd.read_csv(eigengene_file, sep='\t', encoding='utf-8')

                # Column name for this module's eigengene (e.g., "MEturquoise")
                eigengene_col = f"ME{module_id}"

                if eigengene_col in eigengene_df.columns:
                    # Extract eigengene values for this module
                    eigengene_values = eigengene_df[eigengene_col].tolist()
            except Exception as e:
                logger.error(f"❌ [WGCNA] Failed to read eigengene file: {e}")

        logger.info(f"✅ [WGCNA] Returned {len(genes_data)} genes (page {page}/{total_pages})")

        return jsonify({
            'module_id': module_id,
            'gene_count': len(genes_data),  # 하위 호환성
            'total_genes': filtered_total,
            'showing_genes': len(genes_data),
            'current_page': page,
            'total_pages': total_pages,
            'page_size': limit,
            'genes': genes_data,
            'samples': samples,
            'eigengene_values': eigengene_values,
            'is_search_result': bool(search_query),
            'search_query': search_query
        }), 200

    except Exception as e:
        logger.exception(f"❌ [WGCNA] Get module data failed")
        return jsonify({'error': str(e)}), 500
