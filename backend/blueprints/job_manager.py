"""
VizR Job Manager Blueprint
"""
from flask import Blueprint, request, jsonify, session, current_app
import sqlite3
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from queue import Empty
from backend.pipeline.utils.redis_broker import get_redis_broker


def format_json_tree(data, prefix="", is_last=True, max_depth=8, current_depth=0):
    """JSON 데이터를 tree 형태로 포맷팅"""
    if current_depth >= max_depth:
        return f"{prefix}{'└── ' if is_last else '├── '}[Max depth reached]"
    
    lines = []
    
    if isinstance(data, dict):
        items = list(data.items())
        for i, (key, value) in enumerate(items):
            is_last_item = (i == len(items) - 1)
            connector = "└── " if is_last_item else "├── "
            
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{prefix}{connector}{key}:")
                extension = "    " if is_last_item else "│   "
                child_lines = format_json_tree(value, prefix + extension, True, max_depth, current_depth + 1)
                lines.extend(child_lines.split('\n') if isinstance(child_lines, str) else child_lines)
            else:
                # 값이 문자열이고 너무 길면 잘라서 표시
                if isinstance(value, str) and len(value) > 50:
                    display_value = f"{value[:47]}..."
                else:
                    display_value = str(value)
                lines.append(f"{prefix}{connector}{key}: {display_value}")
                
    elif isinstance(data, list):
        for i, item in enumerate(data):
            is_last_item = (i == len(data) - 1)
            connector = "└── " if is_last_item else "├── "
            
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{prefix}{connector}[{i}]:")
                extension = "    " if is_last_item else "│   "
                child_lines = format_json_tree(item, prefix + extension, True, max_depth, current_depth + 1)
                lines.extend(child_lines.split('\n') if isinstance(child_lines, str) else child_lines)
            else:
                if isinstance(item, str) and len(item) > 50:
                    display_value = f"{item[:47]}..."
                else:
                    display_value = str(item)
                lines.append(f"{prefix}{connector}[{i}]: {display_value}")
    else:
        return [f"{prefix}{'└── ' if is_last else '├── '}{str(data)}"]
    
    return lines

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Create blueprint
job_manager_bp = Blueprint('job_manager', __name__, url_prefix='/api/pipeline')

from backend.pipeline.job_generator import PipelineJobGenerator
from backend.pipeline.job_manager import PipelineJobManager

# Global job management instances
job_manager = None

# Import database stuff
from backend.utils.database import get_db_connection


# Authentication helpers
def require_auth(f):
    """Decorator to require authentication for routes."""
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

@job_manager_bp.route('/jobs', methods=['POST'])
def create_pipeline_job():
    """워크벤치에 대한 파이프라인 Job 생성 (사용자 명시적 요청 시에만)"""
    
    try:
        data = request.json
        
        # 요청 데이터를 상세히 로깅 (JSON 형식으로)
        logger.info("🚀 " + "═" * 80)
        logger.info("🚀 PIPELINE JOB CREATION - FUNCTION ENTRY")
        logger.info("🚀 " + "═" * 80)
        logger.info("📥 Receiving pipeline job creation request...")
        
        workbench_id = data.get('workbench_id')
        force_create = data.get('force_create', False)  # 강제 생성 옵션
        
        if not workbench_id:
            return jsonify({'error': 'workbench_id is required'}), 400
        
        with get_db_connection() as conn:
            # 워크벤치 존재 확인
            workbench = conn.execute('''
                SELECT id, name FROM vizr_workbench WHERE id = ?
            ''', (workbench_id,)).fetchone()

            if not workbench:
                return jsonify({'error': 'Workbench not found'}), 404
            
            # Job 생성
            if job_manager.job_generator is None:
                return jsonify({'error': 'Job management system not available'}), 503
            job_id = job_manager.job_generator.create_pipeline_job(workbench_id)
            
            return jsonify({
                'message': 'Pipeline job created successfully',
                'job_id': job_id,
                'workbench_id': workbench_id,
                'workbench_name': workbench['name'],
                'created_by': 'user_request',  # 명시적으로 사용자 요청임을 표시
                'status': 'queued'
            })
        
    except Exception as e:
        logger.error(f"Failed to create pipeline job for workbench {workbench_id}: {e}")
        return jsonify({'error': str(e)}), 500

@job_manager_bp.route('/jobs/<job_id>', methods=['GET'])
def get_pipeline_job_status(job_id):
    """파이프라인 Job 상태 조회"""
    
    try:
        if not job_manager:
            return jsonify({'error': 'Job manager not available'}), 503
        
        job_status = job_manager.get_job_status(job_id)
        
        if not job_status:
            return jsonify({
                'error': 'Job not found',
                'message': 'This job may have been deleted or never existed',
                'should_stop_polling': True  # 프론트엔드에 polling 중단 신호
            }), 404
        
        return jsonify(job_status)
        
    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        return jsonify({'error': str(e)}), 500

@job_manager_bp.route('/jobs/<job_id>', methods=['DELETE'])
def cancel_pipeline_job(job_id):
    """파이프라인 Job 취소"""
    try:
        if not job_manager:
            return jsonify({'error': 'Job manager not available'}), 503
        
        success = job_manager.cancel_pipeline_job(job_id)
        
        if success:
            return jsonify({'message': 'Job cancelled successfully'})
        else:
            return jsonify({'error': 'Failed to cancel job'}), 400
        
    except Exception as e:
        logger.error(f"Failed to cancel job: {e}")
        return jsonify({'error': str(e)}), 500

@job_manager_bp.route('/jobs', methods=['GET'])
def list_pipeline_jobs():
    """파이프라인 Job 목록 조회"""
    try:
        workbench_id = request.args.get('workbench_id', type=int)
        status_filter = request.args.get('status')
        
        conn = get_db_connection()
        
        # job_dashboard 뷰가 제거되어 pipeline_job_steps에서 직접 조회
        query = '''
            SELECT 
                pjs.job_id,
                pjs.workbench_id,
                vw.name as workbench_name,
                COUNT(*) as total_steps,
                SUM(CASE WHEN pjs.status = 'completed' THEN 1 ELSE 0 END) as completed_steps,
                SUM(CASE WHEN pjs.status = 'failed' THEN 1 ELSE 0 END) as failed_steps,
                SUM(CASE WHEN pjs.status = 'running' THEN 1 ELSE 0 END) as running_steps,
                MIN(pjs.created_at) as created_at,
                MAX(pjs.updated_at) as updated_at,
                CASE 
                    WHEN SUM(CASE WHEN pjs.status = 'failed' THEN 1 ELSE 0 END) > 0 THEN 'failed'
                    WHEN SUM(CASE WHEN pjs.status = 'running' THEN 1 ELSE 0 END) > 0 THEN 'running'
                    WHEN COUNT(*) = SUM(CASE WHEN pjs.status = 'completed' THEN 1 ELSE 0 END) THEN 'completed'
                    ELSE 'pending'
                END as status
            FROM pipeline_job_steps pjs
            LEFT JOIN vizr_workbench vw ON pjs.workbench_id = vw.id
            WHERE 1=1
        '''
        params = []
        
        if workbench_id:
            query += ' AND pjs.workbench_id = ?'
            params.append(workbench_id)
        
        # GROUP BY 절 추가
        query += ' GROUP BY pjs.job_id, pjs.workbench_id, vw.name'
        
        if status_filter:
            query += ' HAVING status = ?'
            params.append(status_filter)
        
        query += ' ORDER BY created_at DESC LIMIT 50'
        
        jobs = conn.execute(query, params).fetchall()
        conn.close()
        
        return jsonify([dict(job) for job in jobs])
        
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        return jsonify({'error': str(e)}), 500

@job_manager_bp.route('/jobs/<job_id>/steps', methods=['GET'])
def get_job_steps(job_id):
    """Job의 스텝 상세 정보 조회"""
    try:
        conn = get_db_connection()
        
        steps = conn.execute('''
            SELECT 
                step_id, step_name, tool_name, step_order, status,
                depends_on, input_files, output_files, parameters,
                started_at, completed_at, duration_seconds,
                exit_code, error_message,
                created_at, updated_at
            FROM pipeline_job_steps 
            WHERE job_id = ? 
            ORDER BY step_order
        ''', (job_id,)).fetchall()
        
        conn.close()
        
        if not steps:
            return jsonify({'error': 'Job not found or no steps'}), 404
        
        step_list = []
        for step in steps:
            step_dict = dict(step)
            # JSON 문자열을 파싱
            if step_dict['depends_on']:
                step_dict['depends_on'] = json.loads(step_dict['depends_on'])
            if step_dict['input_files']:
                step_dict['input_files'] = json.loads(step_dict['input_files'])
            if step_dict['output_files']:
                step_dict['output_files'] = json.loads(step_dict['output_files'])
            if step_dict['parameters']:
                step_dict['parameters'] = json.loads(step_dict['parameters'])
            
            step_list.append(step_dict)
        
        return jsonify(step_list)
        
    except Exception as e:
        logger.error(f"Failed to get job steps: {e}")
        return jsonify({'error': str(e)}), 500

@job_manager_bp.route('/jobs/<job_id>/logs', methods=['GET'])
def get_job_logs(job_id):
    """Job 실행 로그 조회"""
    try:
        conn = get_db_connection()
        
        # Job 이벤트 로그
        events = conn.execute('''
            SELECT event_type, message, severity, created_at, step_id, metadata
            FROM job_events 
            WHERE job_id = ? 
            ORDER BY created_at DESC
            LIMIT 100
        ''', (job_id,)).fetchall()
        
        # 스텝별 실행 로그
        step_logs = conn.execute('''
            SELECT step_id, step_name, stdout_log, stderr_log, error_message,
                   started_at, completed_at, exit_code
            FROM pipeline_job_steps 
            WHERE job_id = ? AND (stdout_log IS NOT NULL OR stderr_log IS NOT NULL)
            ORDER BY step_order
        ''', (job_id,)).fetchall()
        
        conn.close()
        
        return jsonify({
            'events': [dict(event) for event in events],
            'step_logs': [dict(log) for log in step_logs]
        })
        
    except Exception as e:
        logger.error(f"Failed to get job logs: {e}")
        return jsonify({'error': str(e)}), 500

@job_manager_bp.route('/system/status', methods=['GET'])
def get_system_status():
    """파이프라인 시스템 상태 조회"""
    try:
        if not job_manager:
            return jsonify({
                'manager_status': 'not_running',
                'error': 'Job manager not initialized'
            })
        
        status = job_manager.get_system_status()
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        return jsonify({'error': str(e)}), 500


@job_manager_bp.route('/jobs/<job_id>/resource-usage', methods=['GET'])
def get_resource_usage(job_id):
    """Job의 리소스 사용량 조회"""
    try:
        step_id = request.args.get('step_id')
        
        conn = get_db_connection()
        
        query = '''
            SELECT 
                step_id, cpu_usage_percent, memory_usage_mb, 
                disk_usage_mb, peak_memory_mb, measured_at
            FROM resource_usage 
            WHERE job_id = ?
        '''
        params = [job_id]
        
        if step_id:
            query += ' AND step_id = ?'
            params.append(step_id)
        
        query += ' ORDER BY measured_at DESC LIMIT 500'
        
        usage_data = conn.execute(query, params).fetchall()
        conn.close()
        
        return jsonify([dict(usage) for usage in usage_data])
        
    except Exception as e:
        logger.error(f"Failed to get resource usage: {e}")
        return jsonify({'error': str(e)}), 500

def initialize_job_management(app_instance=None):
    """Initialize job generator and manager instances"""
    global job_generator, job_manager
    

    
    try:
        # Initialize job manager with ToolManager from app
        
        # app_instance가 전달된 경우 직접 사용, 없으면 current_app 사용
        if app_instance:
            tool_manager = getattr(app_instance, 'tool_manager', None)
        else:
            tool_manager = getattr(current_app, 'tool_manager', None)
            
        # ToolManager 사용 여부에 관계없이 PipelineJobManager 생성
        
        job_manager = PipelineJobManager(max_workers=2, tool_manager=tool_manager)
        job_manager.start()
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize job management: {e}")
        import traceback
        return False

def start_job_manager(app_instance=None):
    """Start job manager - called from main application"""
    return initialize_job_management(app_instance)


@job_manager_bp.route('/workbench/<int:workbench_id>/stop-analysis', methods=['POST'])
def stop_analysis(workbench_id):
    """특정 워크벤치의 분석 중단 - 단순화된 worker_status 방식"""
    try:
        # SharedState import
        from backend.pipeline.utils.shared_state import shared_state
        from backend.utils.database import get_db_connection
        
        with get_db_connection() as conn:
            # 1. 실행 중인 작업들 조회
            running_jobs = conn.execute('''
                SELECT id, job_id, step_id, tool_name, status, worker_id
                FROM pipeline_job_steps 
                WHERE workbench_id = ? AND status IN ('running', 'pending')
            ''', (workbench_id,)).fetchall()
            

            # 2. job_queue에서 해당 workbench의 작업들 삭제
            cancelled_queue_jobs = conn.execute('''
                DELETE FROM job_queue 
                WHERE workbench_id = ?
            ''', (workbench_id,))
            
            logger.info(f"🚫 [STOP-API] Deleted {cancelled_queue_jobs.rowcount} jobs from queue")
            
            # 3. 해당 워크벤치의 실행 중인 워커들을 'stop' 상태로 설정
            stopped_workers = 0
            worker_ids = set()
            
            # running_jobs에서 worker_id 추출
            for job in running_jobs:
                if job['worker_id']:
                    worker_ids.add(job['worker_id'])
            
            
            # ✅ 각 워커에 Event 기반 stop 신호 전송
            for worker_id in worker_ids:
                try:
                    shared_state.set_worker_stop(worker_id)
                    stopped_workers += 1
                except ValueError as e:
                    pass
            
            time.sleep(1.0)  # 워커들이 stop 신호를 처리할 시간
            
            # 4. 데이터베이스 상태 업데이트 - 실행 중인 작업들 중단 상태로 변경
            conn.execute('''
                UPDATE pipeline_job_steps
                SET status = 'cancelled',
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = 'Analysis stopped by user'
                WHERE workbench_id = ? AND status IN ('running', 'pending')
            ''', (workbench_id,))

            # 5. 워크벤치 상태 업데이트
            conn.execute('''
                UPDATE vizr_workbench
                SET status = 'stopped',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (workbench_id,))

            # 6. 이벤트 로그 기록
            conn.execute('''
                INSERT INTO job_events (
                    job_id, workbench_id, event_type, message, severity, 
                    metadata, created_at
                ) VALUES (?, ?, 'user_stop', 'Analysis stopped by user', 'info', 
                         ?, CURRENT_TIMESTAMP)
            ''', ('STOP_REQUEST', workbench_id, f'{{"stopped_jobs": {len(running_jobs)}, "stopped_workers": {stopped_workers}}}'))

            conn.commit()

            logger.info(f"   ├─ Cancelled {len(running_jobs)} jobs")
            logger.info(f"   ├─ Set {stopped_workers} workers to stop status")
            logger.info(f"   └─ Cleared job queue")

            return jsonify({
                'success': True,
                'message': 'Analysis stopped successfully', 
                'stopped_jobs': len(running_jobs),
                'stopped_workers': stopped_workers,
                'workbench_id': workbench_id
            })

    except Exception as e:
        logger.error(f"❌ [STOP-API] Stop analysis failed for workbench {workbench_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@job_manager_bp.route('/workbench/<int:workbench_id>/progress', methods=['GET'])
def get_workbench_progress(workbench_id):
    """워크벤치의 실시간 진행상황 조회 (레거시 폴링용)"""
    try:
        from backend.pipeline.utils.shared_state import shared_state
        
        # SharedState에서 모든 진행상황 데이터 가져오기
        all_progress = shared_state.get_all_progress_data()
        
        # 해당 워크벤치의 진행상황만 필터링
        workbench_progress = {}
        
        for worker_id, worker_progress in all_progress.items():
            # worker_id에서 workbench_id 추출 (예: "worker_1_wb_123")
            if f"wb_{workbench_id}" in worker_id:
                workbench_progress[worker_id] = worker_progress
        
        return jsonify({
            'success': True,
            'workbench_id': workbench_id,
            'progress_data': workbench_progress,
            'timestamp': time.time()
        })
        
    except Exception as e:
        logger.error(f"❌ [PROGRESS-API] Get progress failed for workbench {workbench_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@job_manager_bp.route('/progress/all', methods=['GET'])
def get_all_progress():
    """모든 워크벤치의 실시간 진행상황 조회"""
    try:
        from backend.pipeline.utils.shared_state import shared_state
        
        # SharedState에서 모든 진행상황 데이터 가져오기
        all_progress = shared_state.get_all_progress_data()
        
        return jsonify({
            'success': True,
            'progress_data': all_progress,
            'timestamp': time.time()
        })
        
    except Exception as e:
        logger.error(f"❌ [PROGRESS-API] Get all progress failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@job_manager_bp.route('/worker/<worker_id>/progress', methods=['GET'])
def get_worker_progress(worker_id):
    """특정 워커의 실시간 진행상황 조회"""
    try:
        from backend.pipeline.utils.shared_state import shared_state
        
        # 선택적 task_type 파라미터
        task_type = request.args.get('task_type')
        
        # SharedState에서 워커의 진행상황 데이터 가져오기
        worker_progress = shared_state.get_progress_data(worker_id, task_type)
        
        return jsonify({
            'success': True,
            'worker_id': worker_id,
            'task_type': task_type,
            'progress_data': worker_progress,
            'timestamp': time.time()
        })
        
    except Exception as e:
        logger.error(f"❌ [PROGRESS-API] Get worker progress failed for {worker_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500




