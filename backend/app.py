#!/usr/bin/env python3
"""
VizR - RNASeq Visualization Tool
Flask Backend Application

A comprehensive RNA-Seq analysis and visualization platform supporting
Trinity pipeline, file uploads, NCBI downloads, and interactive data visualization.
"""

import os
import sys
import logging
import threading
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO

# Add parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def create_app():
    """Flask 애플리케이션 팩토리 함수 (WebSocket 지원)"""
    
    # Import modules needed for app creation
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    from werkzeug.security import generate_password_hash, check_password_hash
    from werkzeug.utils import secure_filename
    import hashlib
    import json
    import subprocess
    import time
    from typing import List, Dict, Any, Optional
    
    # Import blueprints
    from backend.blueprints.api import api_bp
    from backend.blueprints.auth import auth_bp
    from backend.blueprints.dashboard import dashboard_bp
    from backend.blueprints.ncbi import ncbi_bp
    from backend.blueprints.macrogen import macrogen_bp
    from backend.blueprints.upload import upload_bp
    from backend.blueprints.server import server_bp
    from backend.blueprints.workbench_core import workbench_core_bp
    from backend.blueprints.workbench_detail_qc import workbench_detail_qc_bp
    from backend.blueprints.workbench_detail_preprocessing import workbench_detail_preprocessing_bp
    from backend.blueprints.workbench_detail_alignment import workbench_detail_alignment_bp
    from backend.blueprints.workbench_share import workbench_share_bp
    from backend.blueprints.workbench_detail_deg import deg_bp
    from backend.blueprints.workbench_detail_counts import counts_bp
    from backend.blueprints.workbench_detail_gsea import gsea_bp
    from backend.blueprints.workbench_detail_pca import pca_bp
    from backend.blueprints.workbench_detail_clustering import clustering_bp
    from backend.blueprints.job_manager import job_manager_bp
    from backend.blueprints.settings import settings_bp
    from backend.blueprints.pattern_analysis import pattern_bp
    from backend.blueprints.interesting_genes import interesting_genes_bp
    from backend.blueprints.client_logs import client_logs_bp
    
    # Import configuration and database utilities
    from config.backend_settings import BackendConfig as Config
    from backend.utils.database import get_db_connection, init_database
    
    # Create Flask app
    app = Flask(__name__)
    app.config['SECRET_KEY'] = Config.SECRET_KEY
    app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH
    
    # Note: User-specific workbench directories are created when workbenches are created
    # No global WORKBENCH_FOLDER needed

    # Enable CORS for frontend development (WebSocket 지원)
    # 개발 환경에서는 모든 origin 허용, 프로덕션에서는 제한
    CORS(app,
         supports_credentials=True,
         origins='*',
         allow_headers=['Content-Type', 'Cache-Control', 'Authorization'],
         expose_headers=['Cache-Control'])
    
    # Initialize Flask-SocketIO (WebSocket 지원)
    # 개발 환경에서는 모든 origin 허용, 프로덕션에서는 제한
    socketio = SocketIO(
        app,
        cors_allowed_origins='*',
        async_mode='threading',
        logger=False,  # SocketIO 로그 비활성화
        engineio_logger=False  # Engine.IO 로그는 너무 상세하므로 비활성화
    )
    
    # Register blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(ncbi_bp)
    app.register_blueprint(macrogen_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(server_bp)
    app.register_blueprint(workbench_core_bp)
    app.register_blueprint(workbench_detail_qc_bp)
    app.register_blueprint(workbench_detail_preprocessing_bp)
    app.register_blueprint(workbench_detail_alignment_bp)
    app.register_blueprint(workbench_share_bp)
    app.register_blueprint(deg_bp)
    app.register_blueprint(pca_bp)
    app.register_blueprint(counts_bp)
    app.register_blueprint(gsea_bp)
    app.register_blueprint(clustering_bp)
    app.register_blueprint(job_manager_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(pattern_bp)
    app.register_blueprint(interesting_genes_bp)
    app.register_blueprint(client_logs_bp)
    
    # Initialize WebSocket handlers
    from backend.blueprints.websocket import init_websocket
    init_websocket(socketio)
    
    from backend.utils.logger import setup_module_logger
    logger = setup_module_logger(__name__, 'INFO')
    logger.info("All blueprints registered successfully: API, Auth, Dashboard, NCBI, Macrogen, Upload, Server, WorkbenchCore, WorkbenchDetailQC, WorkbenchDetailPreprocessing, WorkbenchDetailAlignment, WorkbenchShare, DEG, GSEA, PCA, Counts, Clustering, JobManager, Settings, Pattern, InterestingGenes, ClientLogs, and WebSocket")

    # User-specific workbench directories are created when workbenches are created
    # No global workbench folder initialization needed

    # Static file serving for production (built frontend)
    STATIC_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_frontend(path):
        """Serve static files from frontend build directory"""
        if path != "" and os.path.exists(os.path.join(STATIC_FOLDER, path)):
            return send_from_directory(STATIC_FOLDER, path)
        else:
            # Serve index.html for client-side routing
            return send_from_directory(STATIC_FOLDER, 'index.html')

    # Initialize ToolManager for pipeline jobs
    from backend.pipeline.tool_manager import ToolManager
    logger.info("🔌 [APP] Initializing ToolManager...")
    app.tool_manager = ToolManager()
    logger.info(f"✅ [APP] ToolManager initialized with {len(app.tool_manager.coordinators)} coordinators")
    
    # Error handlers
    @app.errorhandler(413)
    def too_large(e):
        return jsonify({'error': 'File too large'}), 413

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Endpoint not found'}), 404

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error: {e}")
        return jsonify({'error': 'Internal server error'}), 500
    
    return app, socketio

def main():
    """메인 실행 함수"""

    # Setup unified logging system
    from backend.utils.logger import setup_module_logger
    logger = setup_module_logger(__name__, 'INFO')

    # werkzeug 로거 끄기
    werkzeug_log = logging.getLogger('werkzeug')
    werkzeug_log.setLevel(logging.ERROR)  # ERROR 이상만 출력 (INFO, DEBUG는 숨김)

    logger.info("Starting VizR Backend Server with WebSocket support...")
    
    # Import pipeline job management modules (optional)
    try:
        from backend.pipeline.job_generator import PipelineJobGenerator
        from backend.pipeline.job_manager import PipelineJobManager
        from backend.blueprints.job_manager import start_job_manager
        JOB_MANAGEMENT_AVAILABLE = True
        logger.info("Pipeline job management modules loaded successfully")
    except ImportError as e:
        logger.warning(f"Pipeline job management not available: {e}")
        logger.info("Install missing dependencies: pip install psutil")
        PipelineJobGenerator = None
        PipelineJobManager = None
        start_job_manager = None
        JOB_MANAGEMENT_AVAILABLE = False
    
    # Create Flask application with WebSocket support
    app, socketio = create_app()
    
    # Initialize database
    from backend.utils.database import init_database
    init_database()
    
    # Initialize subscription manager
    from backend.utils.subscription_manager import get_subscription_manager
    subscription_manager = get_subscription_manager()
    logger.info("Subscription Manager initialized")
    
    # Initialize pipeline job management (if available)
    job_generator = PipelineJobGenerator() if JOB_MANAGEMENT_AVAILABLE else None
    job_manager = None  # Will be initialized in a separate thread
    
    # Start job manager in background thread with app instance
    if start_job_manager:
        job_manager_thread = threading.Thread(target=start_job_manager, args=(app,))
        job_manager_thread.daemon = True
        job_manager_thread.start()
    
    # Run Flask app with WebSocket support
    # 환경변수로 포트 설정 가능 (기본값: 5001)
    backend_port = int(os.getenv('FLASK_PORT', 5001))
    logger.info(f"Starting Flask server on port {backend_port}")

    socketio.run(
        app,
        host='0.0.0.0',
        port=backend_port,
        debug=True,
        use_reloader=False,  # Auto-reload 비활성화
        allow_unsafe_werkzeug=True  # Docker 환경에서 Werkzeug 허용
    )

if __name__ == '__main__':
    main()
