"""
Interesting Genes API
관심 유전자 셋 관리 및 조회 API
"""

import os
import shutil
from flask import Blueprint, jsonify, request, session
from werkzeug.utils import secure_filename
from backend.utils.logger import setup_module_logger
from config.shared_config import SharedConfig

logger = setup_module_logger(__name__, 'INFO')

interesting_genes_bp = Blueprint('interesting_genes', __name__, url_prefix='/api/interesting-genes')


def require_auth(f):
    """Decorator to require authentication for routes."""
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


def ensure_interesting_genes_directory():
    """
    사용자별 interesting_genes 디렉토리 경로 반환

    사용자 생성 시 resource 폴더와 함께 복사되므로 복사 로직 없음
    경로: VIZR_PATH/users/{username}/resource/arabidopsis/interesting_genes

    Returns:
        str: interesting_genes 디렉토리 경로

    Raises:
        ValueError: 세션에 username이 없는 경우
        FileNotFoundError: interesting_genes 디렉토리가 존재하지 않는 경우
    """
    # 현재 로그인한 사용자의 username 가져오기
    username = session.get('username')
    if not username:
        logger.error(f"❌ [INTERESTING-GENES] No username found in session")
        raise ValueError("Authentication required: username not found in session")

    # 사용자별 경로 생성: VIZR_PATH/users/{username}/resource/arabidopsis/interesting_genes
    base_vizr_path = SharedConfig.VIZR_PATH
    target_dir = f"{base_vizr_path}/users/{username}/resource/arabidopsis/interesting_genes"

    logger.debug(f"[INTERESTING-GENES] Username: {username}")
    logger.debug(f"[INTERESTING-GENES] Target directory: {target_dir}")

    # 디렉토리 확인
    if not os.path.exists(target_dir):
        logger.error(f"❌ [INTERESTING-GENES] Directory not found: {target_dir}")
        logger.error(f"   This should have been created during user registration.")
        raise FileNotFoundError(f"Interesting genes directory not found: {target_dir}")

    logger.info(f"✅ [INTERESTING-GENES] Directory found: {target_dir}")
    return target_dir


def scan_directory_tree(directory: str, base_path: str = None):
    """
    디렉토리를 재귀적으로 스캔하여 트리 구조 생성

    Args:
        directory: 스캔할 디렉토리 경로
        base_path: 상대 경로 계산을 위한 기준 경로

    Returns:
        list: 트리 노드 리스트 [{name, type, path, children}]
    """
    if base_path is None:
        base_path = directory

    tree_nodes = []

    try:
        # 디렉토리 내용 읽기
        entries = os.listdir(directory)
        entries.sort()  # 알파벳 순 정렬

        for entry in entries:
            full_path = os.path.join(directory, entry)
            relative_path = os.path.relpath(full_path, base_path)

            # 숨김 파일/디렉토리 제외
            if entry.startswith('.'):
                continue

            if os.path.isdir(full_path):
                # 폴더
                children = scan_directory_tree(full_path, base_path)
                tree_nodes.append({
                    'name': entry,
                    'type': 'folder',
                    'path': relative_path,
                    'children': children
                })
            elif entry.endswith('.txt'):
                # .txt 파일만 포함 (.txt 확장자 제거)
                display_name = entry[:-4]  # .txt 제거
                tree_nodes.append({
                    'name': display_name,
                    'type': 'file',
                    'path': relative_path,
                    'fullName': entry  # 원본 파일명
                })

    except Exception as e:
        logger.error(f"❌ [INTERESTING-GENES] Failed to scan directory {directory}: {str(e)}")

    return tree_nodes


@interesting_genes_bp.route('/tree', methods=['GET'])
@require_auth
def get_tree():
    """
    interesting_genes 디렉토리 트리 구조 조회

    Response:
        {
            "success": true,
            "tree": [
                {
                    "name": "arabidopsis_2024_03_06",
                    "type": "folder",
                    "path": "arabidopsis_2024_03_06",
                    "children": [
                        {
                            "name": "TF",
                            "type": "folder",
                            "path": "arabidopsis_2024_03_06/TF",
                            "children": [
                                {
                                    "name": "WRKY",
                                    "type": "file",
                                    "path": "arabidopsis_2024_03_06/TF/WRKY.txt",
                                    "fullName": "WRKY.txt"
                                },
                                ...
                            ]
                        },
                        ...
                    ]
                }
            ]
        }
    """
    try:
        # interesting_genes 디렉토리 확인 및 생성
        interesting_genes_dir = ensure_interesting_genes_directory()

        # 트리 구조 스캔
        logger.info(f"🔍 [INTERESTING-GENES] Scanning directory tree: {interesting_genes_dir}")
        tree = scan_directory_tree(interesting_genes_dir)

        logger.info(f"✅ [INTERESTING-GENES] Tree scan completed: {len(tree)} root nodes")

        return jsonify({
            'success': True,
            'tree': tree
        }), 200

    except FileNotFoundError as e:
        logger.error(f"❌ [INTERESTING-GENES] Directory not found: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

    except Exception as e:
        logger.error(f"❌ [INTERESTING-GENES] Failed to get tree: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@interesting_genes_bp.route('/genes', methods=['GET'])
@require_auth
def get_genes():
    """
    특정 유전자 셋 파일의 Gene ID 목록 조회

    Query Parameters:
        file_path: 파일 경로 (상대 경로, 예: arabidopsis_2024_03_06/TF/WRKY.txt)

    Response:
        {
            "success": true,
            "genes": ["AT1G13960", "AT5G46350", ...],
            "count": 72,
            "file_path": "arabidopsis_2024_03_06/TF/WRKY.txt"
        }
    """
    try:
        # Query parameter 파싱
        file_path = request.args.get('file_path', '').strip()

        if not file_path:
            return jsonify({
                'success': False,
                'error': 'file_path parameter is required'
            }), 400

        # interesting_genes 디렉토리 확인
        interesting_genes_dir = ensure_interesting_genes_directory()

        # 전체 파일 경로 생성
        full_path = os.path.join(interesting_genes_dir, file_path)

        # 파일 존재 확인
        if not os.path.exists(full_path):
            logger.warning(f"⚠️ [INTERESTING-GENES] File not found: {full_path}")
            return jsonify({
                'success': False,
                'error': f'File not found: {file_path}'
            }), 404

        # 파일 읽기
        logger.info(f"📖 [INTERESTING-GENES] Reading gene list from: {full_path}")

        genes = []
        with open(full_path, 'r', encoding='utf-8') as f:
            for line in f:
                gene_id = line.strip()
                if gene_id:  # 빈 줄 제외
                    genes.append(gene_id)

        logger.info(f"✅ [INTERESTING-GENES] Loaded {len(genes)} genes from {file_path}")

        return jsonify({
            'success': True,
            'genes': genes,
            'count': len(genes),
            'file_path': file_path
        }), 200

    except Exception as e:
        logger.error(f"❌ [INTERESTING-GENES] Failed to get genes: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@interesting_genes_bp.route('/create', methods=['POST'])
@require_auth
def create_gene_set():
    """
    새 유전자 셋 파일 생성

    Request Body:
        {
            "folder_path": "arabidopsis_2024_03_06/TF",  # 상대 경로
            "file_name": "MY_GENES",  # .txt 없이
            "genes": ["AT1G01010", "AT1G01020", ...]
        }

    Response:
        {
            "success": true,
            "file_path": "arabidopsis_2024_03_06/TF/MY_GENES.txt",
            "gene_count": 150
        }
    """
    try:
        # Request body 파싱
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400

        folder_path = data.get('folder_path', '').strip()
        file_name = data.get('file_name', '').strip()
        genes = data.get('genes', [])

        if not folder_path or not file_name:
            return jsonify({
                'success': False,
                'error': 'folder_path and file_name are required'
            }), 400

        if not genes or not isinstance(genes, list):
            return jsonify({
                'success': False,
                'error': 'genes must be a non-empty list'
            }), 400

        # interesting_genes 디렉토리 확인
        interesting_genes_dir = ensure_interesting_genes_directory()

        # 파일 경로 생성 (.txt 자동 추가)
        if not file_name.endswith('.txt'):
            file_name = f"{file_name}.txt"

        full_folder_path = os.path.join(interesting_genes_dir, folder_path)
        full_file_path = os.path.join(full_folder_path, file_name)

        # 폴더가 없으면 생성
        os.makedirs(full_folder_path, exist_ok=True)

        # 파일이 이미 존재하는지 확인
        if os.path.exists(full_file_path):
            return jsonify({
                'success': False,
                'error': f'File already exists: {file_name}'
            }), 409

        # 파일 생성
        logger.info(f"📝 [INTERESTING-GENES] Creating gene set file: {full_file_path}")

        with open(full_file_path, 'w', encoding='utf-8') as f:
            for gene in genes:
                f.write(f"{gene.strip()}\n")

        relative_path = os.path.join(folder_path, file_name)
        logger.info(f"✅ [INTERESTING-GENES] Gene set created: {relative_path} ({len(genes)} genes)")

        return jsonify({
            'success': True,
            'file_path': relative_path,
            'gene_count': len(genes)
        }), 201

    except Exception as e:
        logger.error(f"❌ [INTERESTING-GENES] Failed to create gene set: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@interesting_genes_bp.route('/update', methods=['PUT'])
@require_auth
def update_gene_set():
    """
    기존 유전자 셋 파일 수정

    Request Body:
        {
            "file_path": "arabidopsis_2024_03_06/TF/MY_GENES.txt",  # 상대 경로
            "genes": ["AT1G01010", "AT1G01020", ...]
        }

    Response:
        {
            "success": true,
            "file_path": "arabidopsis_2024_03_06/TF/MY_GENES.txt",
            "gene_count": 150
        }
    """
    try:
        # Request body 파싱
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400

        file_path = data.get('file_path', '').strip()
        genes = data.get('genes', [])

        if not file_path:
            return jsonify({
                'success': False,
                'error': 'file_path is required'
            }), 400

        if not genes or not isinstance(genes, list):
            return jsonify({
                'success': False,
                'error': 'genes must be a non-empty list'
            }), 400

        # interesting_genes 디렉토리 확인
        interesting_genes_dir = ensure_interesting_genes_directory()

        # 전체 파일 경로 생성
        full_path = os.path.join(interesting_genes_dir, file_path)

        # 파일 존재 확인
        if not os.path.exists(full_path):
            return jsonify({
                'success': False,
                'error': f'File not found: {file_path}'
            }), 404

        # 파일 수정
        logger.info(f"✏️ [INTERESTING-GENES] Updating gene set file: {full_path}")

        with open(full_path, 'w', encoding='utf-8') as f:
            for gene in genes:
                f.write(f"{gene.strip()}\n")

        logger.info(f"✅ [INTERESTING-GENES] Gene set updated: {file_path} ({len(genes)} genes)")

        return jsonify({
            'success': True,
            'file_path': file_path,
            'gene_count': len(genes)
        }), 200

    except Exception as e:
        logger.error(f"❌ [INTERESTING-GENES] Failed to update gene set: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@interesting_genes_bp.route('/delete', methods=['DELETE'])
@require_auth
def delete_gene_set():
    """
    유전자 셋 파일 삭제

    Query Parameters:
        file_path: 파일 경로 (상대 경로, 예: arabidopsis_2024_03_06/TF/MY_GENES.txt)

    Response:
        {
            "success": true,
            "message": "Gene set deleted successfully"
        }
    """
    try:
        # Query parameter 파싱
        file_path = request.args.get('file_path', '').strip()

        if not file_path:
            return jsonify({
                'success': False,
                'error': 'file_path parameter is required'
            }), 400

        # interesting_genes 디렉토리 확인
        interesting_genes_dir = ensure_interesting_genes_directory()

        # 전체 파일 경로 생성
        full_path = os.path.join(interesting_genes_dir, file_path)

        # 파일 존재 확인
        if not os.path.exists(full_path):
            return jsonify({
                'success': False,
                'error': f'File not found: {file_path}'
            }), 404

        # 파일 삭제
        logger.info(f"🗑️ [INTERESTING-GENES] Deleting gene set file: {full_path}")
        os.remove(full_path)

        logger.info(f"✅ [INTERESTING-GENES] Gene set deleted: {file_path}")

        return jsonify({
            'success': True,
            'message': 'Gene set deleted successfully'
        }), 200

    except Exception as e:
        logger.error(f"❌ [INTERESTING-GENES] Failed to delete gene set: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@interesting_genes_bp.route('/delete-folder', methods=['DELETE'])
@require_auth
def delete_folder():
    """
    폴더 삭제 (하위 파일 및 폴더 모두 삭제)

    Query Parameters:
        folder_path: 폴더 경로 (상대 경로, 예: arabidopsis_2024_03_06/TF)

    Response:
        {
            "success": true,
            "message": "Folder deleted successfully"
        }
    """
    try:
        # Query parameter 파싱
        folder_path = request.args.get('folder_path', '').strip()

        if not folder_path:
            return jsonify({
                'success': False,
                'error': 'folder_path parameter is required'
            }), 400

        # interesting_genes 디렉토리 확인
        interesting_genes_dir = ensure_interesting_genes_directory()

        # 전체 폴더 경로 생성
        full_path = os.path.join(interesting_genes_dir, folder_path)

        # 폴더 존재 확인
        if not os.path.exists(full_path):
            return jsonify({
                'success': False,
                'error': f'Folder not found: {folder_path}'
            }), 404

        # 디렉토리가 아닌 경우
        if not os.path.isdir(full_path):
            return jsonify({
                'success': False,
                'error': f'Path is not a folder: {folder_path}'
            }), 400

        # 루트 디렉토리 삭제 방지
        if full_path == interesting_genes_dir:
            return jsonify({
                'success': False,
                'error': 'Cannot delete root directory'
            }), 400

        # 폴더 삭제 (하위 모든 내용 삭제)
        logger.info(f"🗑️ [INTERESTING-GENES] Deleting folder: {full_path}")
        shutil.rmtree(full_path)

        logger.info(f"✅ [INTERESTING-GENES] Folder deleted: {folder_path}")

        return jsonify({
            'success': True,
            'message': 'Folder deleted successfully'
        }), 200

    except Exception as e:
        logger.error(f"❌ [INTERESTING-GENES] Failed to delete folder: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@interesting_genes_bp.route('/upload', methods=['POST'])
@require_auth
def upload_gene_sets():
    """
    폴더 또는 파일 업로드

    Form Data:
        folder_path: 업로드할 대상 폴더 경로 (상대 경로)
        files[]: 업로드할 파일들 (multiple files)

    Response:
        {
            "success": true,
            "uploaded_files": [
                {
                    "original_name": "WRKY.txt",
                    "saved_path": "arabidopsis_2024_03_06/TF/WRKY.txt",
                    "gene_count": 72
                },
                ...
            ],
            "total_count": 5
        }
    """
    try:
        # Form data 파싱
        folder_path = request.form.get('folder_path', '').strip()

        if not folder_path:
            return jsonify({
                'success': False,
                'error': 'folder_path is required'
            }), 400

        # 파일 확인
        if 'files[]' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No files provided'
            }), 400

        files = request.files.getlist('files[]')

        if len(files) == 0:
            return jsonify({
                'success': False,
                'error': 'No files provided'
            }), 400

        # interesting_genes 디렉토리 확인
        interesting_genes_dir = ensure_interesting_genes_directory()

        # 대상 폴더 경로 생성
        base_target_folder = os.path.join(interesting_genes_dir, folder_path)
        os.makedirs(base_target_folder, exist_ok=True)

        uploaded_files = []

        for file in files:
            if file.filename == '':
                continue

            # 파일명 검증 (.txt 파일만 허용)
            if not file.filename.endswith('.txt'):
                logger.warning(f"⚠️ [INTERESTING-GENES] Skipping non-txt file: {file.filename}")
                continue

            # webkitRelativePath가 있으면 사용 (하위 폴더 구조 보존)
            # 형식: "D/SubFolder/File.txt" 또는 "D/File.txt"
            relative_file_path = file.filename

            # Flask의 FileStorage 객체에서 custom attribute 확인
            if hasattr(file, 'filename') and '/' in file.filename:
                # 이미 파일명에 경로가 포함되어 있는 경우
                relative_file_path = file.filename

            # 경로 구분자로 분리
            path_parts = relative_file_path.replace('\\', '/').split('/')

            # 안전한 경로 생성 (각 부분을 secure_filename으로 처리)
            safe_path_parts = [secure_filename(part) for part in path_parts]
            safe_relative_path = '/'.join(safe_path_parts)

            # 최종 파일 경로
            file_path = os.path.join(base_target_folder, *safe_path_parts)

            # 하위 폴더가 있으면 생성
            file_dir = os.path.dirname(file_path)
            if file_dir:
                os.makedirs(file_dir, exist_ok=True)

            # 상대 경로 (응답용)
            relative_path = os.path.join(folder_path, safe_relative_path).replace('\\', '/')

            # 파일이 이미 존재하는지 확인
            if os.path.exists(file_path):
                logger.warning(f"⚠️ [INTERESTING-GENES] File already exists, skipping: {relative_path}")
                continue

            # 파일 저장
            file.save(file_path)

            # 유전자 개수 계산
            gene_count = 0
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        gene_count += 1

            uploaded_files.append({
                'original_name': file.filename,
                'saved_path': relative_path,
                'gene_count': gene_count
            })

            logger.info(f"✅ [INTERESTING-GENES] Uploaded: {relative_path} ({gene_count} genes)")

        return jsonify({
            'success': True,
            'uploaded_files': uploaded_files,
            'total_count': len(uploaded_files)
        }), 201

    except Exception as e:
        logger.error(f"❌ [INTERESTING-GENES] Failed to upload files: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
