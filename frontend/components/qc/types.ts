// QC Component Type Definitions

export enum SampleStatus {
    PASS = 'PASS',
    WARN = 'WARN',
    FAIL = 'FAIL'
}

// Chart data types for Per base quality
export interface PerBaseQualityData {
    position: string;
    mean: number;
    median: number;
    q25: number;
    q75: number;
    p10: number;
    p90: number;
}

// Chart data types for Per base content
export interface PerBaseContentData {
    position: string;
    G: number;
    A: number;
    T: number;
    C: number;
}

// Generic count data structure
export interface GenericCountData {
    value: number;
    count: number;
}

// Generic distribution data structure
export interface GenericDistributionData {
    name: string;
    value: number;
}

// QC Metrics containing all chart data
export interface QCMetrics {
    per_base_quality?: PerBaseQualityData[];
    per_sequence_quality?: GenericCountData[];
    per_base_sequence_content?: PerBaseContentData[];
    per_sequence_gc_content?: GenericCountData[];
    per_base_n_content?: GenericDistributionData[];
    sequence_length_distribution?: GenericCountData[];
    adapter_content?: GenericDistributionData[];
    duplication_levels?: GenericDistributionData[];
}

// Summary information for a sample
export interface Summary {
    totalSequences: string;
    avgLength: number;
    avgQuality: number;
    filename?: string;
}

// Module Statistics
export interface ModuleStatistics {
    pass_count: number;
    warn_count: number;
    fail_count: number;
    total_modules: number;
    module_details: Record<string, { status: string }>;
    failed_modules: string[];
    warned_modules: string[];
}

// AI Analysis Result
export interface AIAnalysis {
    overall_assessment: string;
    confidence_score: number;
    experiment_type: string;
    quality_evaluation: {
        usability: 'excellent' | 'good' | 'fair' | 'poor';
        concerns: string[];
        strengths: string[];
    };
    recommendations: {
        immediate_actions: string[];
        preprocessing: string[];
        downstream_considerations: string[];
    };
    expected_outcomes: {
        alignment_rate: string;
        contamination_risk: string;
        coverage_uniformity: string;
    };
    processing_time?: number;
}

// Main Sample interface
export interface Sample {
    id: string;
    name: string;
    group?: string;
    status?: SampleStatus;  // Made optional since we use statistics now
    statistics?: ModuleStatistics;  // New field for module statistics
    summary: Summary;
    metrics: QCMetrics;
    file_path?: string;
    ai_analysis?: AIAnalysis;  // New field for AI analysis
    ai_analysis_status?: string;  // AI analysis status (success, error, skipped)
    ai_analysis_reason?: string;  // Reason for status (e.g., disabled in settings)
}

// Component Props interfaces
export interface QCSidebarProps {
    samples: Sample[];
    selectedSampleId: string | null;
    onSelectSample: (sampleId: string | null) => void;
}

export interface QCSampleOverviewProps {
    samples: Sample[];
    onSelectSample: (sample: Sample) => void;
    moduleStatistics?: ModuleStatistics;
}

export interface QCSampleDetailProps {
    sample: Sample;
}

// Chart component props
export interface ChartContainerProps {
    title: string;
    status?: 'pass' | 'warn' | 'fail';
    children: React.ReactNode;
}

// Statistics interfaces
export interface SampleStatistics {
    total_samples: number;
    passed_samples: number;
    warning_samples: number;
    failed_samples: number;
}

export interface ModuleStatistics {
    total_samples: number;
    total_modules: number;
    passed_modules: number;
    warning_modules: number;
    failed_modules: number;
}

// API Response interface
export interface QCResultsResponse {
    workbench_id: number;
    samples: Sample[];
    total_count: number;
    sample_statistics?: SampleStatistics;
    module_statistics?: ModuleStatistics;
    message?: string;
}