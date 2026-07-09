-- VizR RNASeq Visualization Tool Database Schema
-- SQLite Database for storing workbenches and analysis results

PRAGMA foreign_keys = ON;

-- Users table for authentication
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    settings TEXT, -- JSON format for user settings
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- VizR Workbench table (main workbench entity)
CREATE TABLE vizr_workbench (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    species VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    user_id INTEGER NOT NULL,
    shared_users TEXT DEFAULT '[]', -- JSON array of user IDs that this workbench is shared with
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- VizR Pipeline Configurations table (stores pipeline settings)
CREATE TABLE vizr_pipeline_configurations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workbench_id INTEGER NOT NULL,
    pipeline_steps TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workbench_id) REFERENCES vizr_workbench(id) ON DELETE CASCADE
);

-- VizR Pipeline Samples table (stores sample mappings)
CREATE TABLE vizr_pipeline_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workbench_id INTEGER NOT NULL,
    layout VARCHAR(255),
    samples TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workbench_id) REFERENCES vizr_workbench(id) ON DELETE CASCADE
);

-- Pipeline configuration table (stores pipeline settings)
CREATE TABLE pipeline_configurations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workbench_id INTEGER NOT NULL,
    data_layout VARCHAR(10) NOT NULL, -- 'se' or 'pe'
    trimmomatic_adapter VARCHAR(50) DEFAULT 'TruSeq3-PE-2.fa', -- Trimmomatic adapter option
    illuminaclip_seed_mismatches INTEGER DEFAULT 2, -- ILLUMINACLIP seed mismatches
    illuminaclip_palindrome_clip INTEGER DEFAULT 30, -- ILLUMINACLIP palindrome clip threshold
    illuminaclip_simple_clip INTEGER DEFAULT 10, -- ILLUMINACLIP simple clip threshold
    pipeline_steps TEXT NOT NULL, -- JSON string of pipeline steps configuration
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workbench_id) REFERENCES vizr_workbench(id) ON DELETE CASCADE
);

-- System settings table
CREATE TABLE system_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key VARCHAR(255) UNIQUE NOT NULL,
    value TEXT,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Insert default system settings
-- Pipeline Job Management Tables
-- Job Step 실행 상태 테이블
CREATE TABLE pipeline_job_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id VARCHAR(100) NOT NULL,
    step_id VARCHAR(50) NOT NULL,
    step_name VARCHAR(100) NOT NULL,
    tool_name VARCHAR(50) NOT NULL,
    step_order INTEGER NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    should_run INTEGER DEFAULT 0, -- 이 step이 현재 파이프라인에서 실행되어야 하는지 여부 (0: 실행하지 않음, 1: 실행해야 함)
    workbench_id INTEGER NOT NULL,
    input_files TEXT,
    output_files TEXT,
    input_dir VARCHAR(500),
    output_dir VARCHAR(500),
    parameters TEXT,
    resources_used TEXT,
    progress_detail TEXT DEFAULT NULL, -- JSON format progress data for file downloads
    started_at DATETIME,
    completed_at DATETIME,
    duration_seconds INTEGER,
    exit_code INTEGER,
    stdout_log TEXT,
    stderr_log TEXT,
    error_message TEXT,
    worker_id INTEGER,
    process_pid INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workbench_id) REFERENCES vizr_workbench(id) ON DELETE CASCADE
);

-- Job Queue 테이블 (실행 대기열)
CREATE TABLE job_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id VARCHAR(100) NOT NULL,
    step_id VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'queued',
    priority INTEGER DEFAULT 0,
    worker_id VARCHAR(50),
    workbench_id INTEGER NOT NULL,
    queued_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,
    FOREIGN KEY (workbench_id) REFERENCES vizr_workbench(id) ON DELETE CASCADE
);


CREATE TABLE resource_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id VARCHAR(100) NOT NULL,
    step_id VARCHAR(50) NOT NULL,
    cpu_usage_percent FLOAT,
    memory_usage_mb INTEGER,
    disk_usage_mb INTEGER,
    network_io_mb INTEGER,
    peak_memory_mb INTEGER,
    measured_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id VARCHAR(100) NOT NULL,
    step_id VARCHAR(50),
    workbench_id INTEGER,
    event_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    severity VARCHAR(20) DEFAULT 'info',
    metadata TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workbench_id) REFERENCES vizr_workbench(id) ON DELETE CASCADE
);

INSERT INTO system_settings (key, value, description) VALUES 
('trinity_path', '/usr/local/bin/Trinity', 'Path to Trinity executable'),
('fastqc_path', '/usr/local/bin/fastqc', 'Path to FastQC executable'),
('fastp_path', '/usr/local/bin/fastp', 'Path to fastp executable'),
('sra_toolkit_path', '/usr/local/bin', 'Path to SRA toolkit directory'),
('max_upload_size', '10737418240', 'Maximum file upload size in bytes (10GB)'),
('workbench_base_path', './workbenches', 'Base directory for workbench data storage');

-- Indexes for performance
-- VizR Workbench indexes
CREATE INDEX idx_vizr_workbench_user_id ON vizr_workbench(user_id);
CREATE INDEX idx_vizr_workbench_status ON vizr_workbench(status);
CREATE INDEX idx_vizr_workbench_species ON vizr_workbench(species);
CREATE INDEX idx_vizr_workbench_created_at ON vizr_workbench(created_at);
CREATE INDEX idx_vizr_workbench_user_status ON vizr_workbench(user_id, status);

-- VizR Pipeline Configuration indexes
CREATE INDEX idx_vizr_pipeline_configs_workbench_id ON vizr_pipeline_configurations(workbench_id);
CREATE INDEX idx_vizr_pipeline_configs_created_at ON vizr_pipeline_configurations(created_at);

-- VizR Pipeline Samples indexes
CREATE INDEX idx_vizr_pipeline_samples_workbench_id ON vizr_pipeline_samples(workbench_id);
CREATE INDEX idx_vizr_pipeline_samples_layout ON vizr_pipeline_samples(layout);
CREATE INDEX idx_vizr_pipeline_samples_created_at ON vizr_pipeline_samples(created_at);

-- Pipeline Job Management indexes
CREATE INDEX idx_pipeline_job_steps_job_id ON pipeline_job_steps(job_id);
CREATE INDEX idx_pipeline_job_steps_status ON pipeline_job_steps(status);
CREATE INDEX idx_pipeline_job_steps_workbench_id ON pipeline_job_steps(workbench_id);
CREATE INDEX idx_job_queue_status ON job_queue(status);
CREATE INDEX idx_job_queue_priority ON job_queue(priority DESC);
CREATE INDEX idx_resource_usage_job_step ON resource_usage(job_id, step_id);
CREATE INDEX idx_job_events_job_id ON job_events(job_id);
CREATE INDEX idx_job_events_workbench_id ON job_events(workbench_id);


-- Views for commonly used data
CREATE VIEW workbench_summary AS
SELECT 
    w.id,
    w.name,
    w.description,
    w.species,
    w.status,
    w.user_id,
    w.created_at,
    w.updated_at,
    u.username as created_by
FROM vizr_workbench w
LEFT JOIN users u ON w.user_id = u.id
GROUP BY w.id, w.name, w.description, w.species, w.status, w.user_id, w.created_at, w.updated_at, 
         u.username;

CREATE VIEW recent_workbenches AS
SELECT 
    ws.*
FROM workbench_summary ws
ORDER BY ws.updated_at DESC
LIMIT 10;

-- Triggers for updating timestamps
CREATE TRIGGER tr_vizr_workbench_updated_at
    AFTER UPDATE ON vizr_workbench
    FOR EACH ROW
BEGIN
    UPDATE vizr_workbench SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER tr_vizr_pipeline_configs_updated_at
    AFTER UPDATE ON vizr_pipeline_configurations
    FOR EACH ROW
BEGIN
    UPDATE vizr_pipeline_configurations SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;