import React, { useState, useEffect } from 'react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, LineChart, Line, PieChart, Pie, Cell } from 'recharts';
import useWebSocket from '../src/hooks/useWebSocket';
import { Workbench, StepDetail } from '../types';
import { QCSidebar, QCSampleOverview, QCSampleDetail, Sample, QCResultsResponse, SampleStatus, SampleStatistics, ModuleStatistics } from './qc';

// ========================================
// Type Definitions
// ========================================

type WSConnectionStatus = 'connecting' | 'connected' | 'error' | 'closed';
type QCAnalysisStatus = 'not_started' | 'running' | 'completing' | 'completed' | 'failed';

interface QCProgressData {
    completed_files: number;
    total_files: number;
    progress_percent: number;
    last_updated?: number;
}

interface QCMetric {
    sample_id: string;
    sample_name: string;
    total_sequences: number;
    poor_quality: number;
    sequence_length: string;
    gc_content: number;
    per_base_quality: number[];
    per_sequence_quality_scores: number[];
    overrepresented_sequences: string[];
    adapter_content: number;
    duplication_level: number;
}

interface QCResult {
    id: number;
    workbench_id: number;
    sample_id: number;
    sample_name: string;
    fastqc_status: 'pending' | 'running' | 'completed' | 'failed';
    fastqc_report_path?: string;
    fastqc_summary?: any;
    created_at: string;
    updated_at: string;
}

interface WorkbenchDetailQCProps {
    workbench: Workbench;
    pipelineStepsData: StepDetail[];
    executedStepNames: string[];
}

// ========================================
// Helper Functions
// ========================================

/**
 * Generate mock QC data for visualization
 */
const generateMockQCData = (): QCMetric[] => {
    const samples = ['Sample 1', 'Sample 2', 'Sample 3', 'Sample 4', 'Sample 5', 'Sample 6'];
    return samples.map((sample, idx) => ({
        sample_id: `sample_${idx + 1}`,
        sample_name: sample,
        total_sequences: Math.floor(Math.random() * 10000000) + 5000000,
        poor_quality: Math.floor(Math.random() * 5) + 1,
        sequence_length: '50-151',
        gc_content: Math.floor(Math.random() * 10) + 45,
        per_base_quality: Array(151).fill(0).map(() => Math.floor(Math.random() * 10) + 30),
        per_sequence_quality_scores: Array(40).fill(0).map((_, i) => Math.floor(Math.random() * 100000)),
        overrepresented_sequences: [],
        adapter_content: Math.random() * 5,
        duplication_level: Math.random() * 30 + 10
    }));
};

// ========================================
// Sub-Components
// ========================================

/**
 * Quality Score Overview Card
 */
const QualityScoreCard = ({ title, value, unit, color }: { title: string; value: number | string; unit?: string; color: string }) => (
    <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm hover:shadow-md transition-shadow">
        <div className="flex items-center justify-between">
            <div>
                <p className="text-sm text-slate-600 mb-1">{title}</p>
                <p className={`text-2xl font-bold ${color}`}>
                    {value}{unit && <span className="text-lg font-normal ml-1">{unit}</span>}
                </p>
            </div>
            <div className={`w-12 h-12 rounded-full ${color.replace('text', 'bg').replace('600', '100')} flex items-center justify-center`}>
                <span className="text-2xl">
                    {title.includes('Quality') && '✨'}
                    {title.includes('Sequences') && '🧬'}
                    {title.includes('GC') && '🧪'}
                    {title.includes('Length') && '📏'}
                    {title.includes('Duplication') && '🔄'}
                    {title.includes('Adapter') && '🔗'}
                </span>
            </div>
        </div>
    </div>
);

/**
 * Per Base Quality Chart
 */
const PerBaseQualityChart = ({ data }: { data: any[] }) => (
    <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
        <h4 className="text-lg font-semibold text-slate-800 mb-4">Per Base Sequence Quality</h4>
        <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis
                    dataKey="position"
                    label={{ value: 'Position in read (bp)', position: 'insideBottom', offset: -5 }}
                    stroke="#64748b"
                />
                <YAxis
                    label={{ value: 'Quality Score', angle: -90, position: 'insideLeft' }}
                    domain={[0, 40]}
                    stroke="#64748b"
                />
                <Tooltip
                    contentStyle={{
                        backgroundColor: '#ffffff',
                        border: '1px solid #e2e8f0',
                        borderRadius: '8px'
                    }}
                />
                <Legend />
                {/* Quality zones */}
                <Line type="monotone" dataKey="quality" stroke="#06b6d4" strokeWidth={2} dot={false} name="Mean Quality" />
                {/* Add quality threshold lines */}
                <Line type="monotone" dataKey="threshold_good" stroke="#10b981" strokeWidth={1} strokeDasharray="5 5" dot={false} name="Good (>28)" />
                <Line type="monotone" dataKey="threshold_poor" stroke="#ef4444" strokeWidth={1} strokeDasharray="5 5" dot={false} name="Poor (<20)" />
            </LineChart>
        </ResponsiveContainer>
    </div>
);

/**
 * GC Content Distribution
 */
const GCContentChart = ({ data }: { data: any[] }) => (
    <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
        <h4 className="text-lg font-semibold text-slate-800 mb-4">GC Content Distribution</h4>
        <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="sample_name" stroke="#64748b" />
                <YAxis
                    label={{ value: 'GC Content (%)', angle: -90, position: 'insideLeft' }}
                    stroke="#64748b"
                />
                <Tooltip
                    contentStyle={{
                        backgroundColor: '#ffffff',
                        border: '1px solid #e2e8f0',
                        borderRadius: '8px'
                    }}
                />
                <Bar dataKey="gc_content" fill="#8b5cf6" />
            </BarChart>
        </ResponsiveContainer>
    </div>
);

/**
 * QC Progress View Component
 */
const QCProgressView = ({ progress }: { progress: QCProgressData | null }) => {
    const progressPercent = progress?.progress_percent || 0;
    const completedFiles = progress?.completed_files || 0;
    const totalFiles = progress?.total_files || 0;

    return (
        <div className="bg-white rounded-lg border border-slate-200 p-8 shadow-sm">
            <div className="flex items-center justify-center mb-8">
                <div className="text-center max-w-2xl">
                    <span className="text-6xl mb-4 block">🔬</span>
                    <h3 className="text-2xl font-semibold text-slate-800 mb-2">FastQC Analysis in Progress...</h3>
                    <p className="text-slate-600">
                        Quality control analysis is running on your sequencing data.
                        This may take a few minutes depending on the file size.
                    </p>
                </div>
            </div>

            {/* Progress Bar */}
            <div className="max-w-3xl mx-auto mb-6">
                <div className="flex items-center justify-between text-sm text-slate-600 mb-2">
                    <span>Progress</span>
                    <span className="font-medium">{progressPercent.toFixed(1)}%</span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-4 overflow-hidden">
                    <div
                        className="h-full bg-gradient-to-r from-blue-500 to-cyan-500 rounded-full transition-all duration-500 ease-out"
                        style={{ width: `${progressPercent}%` }}
                    >
                        <div className="h-full bg-white/20 animate-pulse"></div>
                    </div>
                </div>
                <div className="flex items-center justify-center mt-4 text-slate-700">
                    <span className="text-lg font-medium">
                        {completedFiles} of {totalFiles} files completed
                    </span>
                </div>
            </div>

            {/* Status Icons */}
            <div className="flex items-center justify-center space-x-8 text-sm">
                <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
                    <span className="text-slate-600">Processing</span>
                </div>
                <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
                    <span className="text-slate-600">Live Updates Active</span>
                </div>
            </div>
        </div>
    );
};

/**
 * QC Completion Celebration View Component
 */
const QCCompletionView = ({ progress }: { progress: QCProgressData | null }) => {
    const completedFiles = progress?.completed_files || 0;
    const totalFiles = progress?.total_files || 0;

    return (
        <div className="bg-gradient-to-br from-green-50 via-emerald-50 to-teal-50 rounded-lg border border-green-200 p-8 shadow-sm">
            <div className="flex items-center justify-center mb-8">
                <div className="text-center max-w-2xl">
                    <div className="text-8xl mb-6 animate-bounce">🎉</div>
                    <h3 className="text-3xl font-bold text-green-800 mb-3">
                        Quality Control Analysis Complete!
                    </h3>
                    <p className="text-lg text-green-700 mb-4">
                        Excellent! Your sequencing data quality analysis has been successfully completed.
                    </p>
                    <p className="text-green-600">
                        All {totalFiles} files have been processed and analyzed.
                        Preparing your quality control report...
                    </p>
                </div>
            </div>

            {/* Completion Stats */}
            <div className="max-w-2xl mx-auto mb-6">
                <div className="bg-white/60 rounded-lg p-4 border border-green-200">
                    <div className="flex items-center justify-between text-green-800">
                        <div className="flex items-center space-x-2">
                            <span className="text-2xl">✅</span>
                            <span className="font-semibold">Files Processed:</span>
                        </div>
                        <span className="text-xl font-bold">{completedFiles} / {totalFiles}</span>
                    </div>
                </div>
            </div>

            {/* Success Indicators */}
            <div className="flex items-center justify-center space-x-8 text-sm">
                <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
                    <span className="text-green-700 font-medium">Analysis Complete</span>
                </div>
                <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
                    <span className="text-green-700 font-medium">Loading Results...</span>
                </div>
            </div>

            {/* Progress completion animation */}
            <div className="max-w-3xl mx-auto mt-6">
                <div className="w-full bg-green-200 rounded-full h-3 overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-green-500 to-emerald-500 rounded-full w-full">
                        <div className="h-full bg-white/30 animate-pulse"></div>
                    </div>
                </div>
            </div>
        </div>
    );
};

/**
 * Quality Status Summary
 */
const QualityStatusSummary = ({ qcResults }: { qcResults: QCResult[] }) => {
    const statusCounts = {
        completed: qcResults.filter(r => r.fastqc_status === 'completed').length,
        running: qcResults.filter(r => r.fastqc_status === 'running').length,
        pending: qcResults.filter(r => r.fastqc_status === 'pending').length,
        failed: qcResults.filter(r => r.fastqc_status === 'failed').length
    };

    const pieData = [
        { name: 'Completed', value: statusCounts.completed, color: '#10b981' },
        { name: 'Running', value: statusCounts.running, color: '#3b82f6' },
        { name: 'Pending', value: statusCounts.pending, color: '#f59e0b' },
        { name: 'Failed', value: statusCounts.failed, color: '#ef4444' }
    ].filter(item => item.value > 0);

    return (
        <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
            <h4 className="text-lg font-semibold text-slate-800 mb-4">QC Analysis Status</h4>
            <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                    <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                        outerRadius={80}
                        fill="#8884d8"
                        dataKey="value"
                    >
                        {pieData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                    </Pie>
                    <Tooltip />
                </PieChart>
            </ResponsiveContainer>
            <div className="grid grid-cols-2 gap-2 mt-4">
                {Object.entries(statusCounts).map(([status, count]) => (
                    <div key={status} className="flex items-center space-x-2 text-sm">
                        <div className={`w-3 h-3 rounded-full ${
                            status === 'completed' ? 'bg-green-500' :
                            status === 'running' ? 'bg-blue-500' :
                            status === 'pending' ? 'bg-yellow-500' : 'bg-red-500'
                        }`} />
                        <span className="text-slate-600 capitalize">{status}:</span>
                        <span className="font-medium text-slate-800">{count}</span>
                    </div>
                ))}
            </div>
        </div>
    );
};

// ========================================
// Main Component
// ========================================

const WorkbenchDetailQC: React.FC<WorkbenchDetailQCProps> = ({
    workbench,
    pipelineStepsData,
    executedStepNames
}) => {
    // ========================================
    // Check if QC step is enabled (based on actual execution, not configuration)
    // ========================================
    const isQCEnabled = executedStepNames.includes('qc');

    // ========================================
    // State Management
    // ========================================

    const [qcData, setQcData] = useState<QCMetric[]>([]);
    const [qcResults, setQcResults] = useState<QCResult[]>([]);
    const [samples, setSamples] = useState<Sample[]>([]);
    const [wsStatus, setWsStatus] = useState<WSConnectionStatus>('closed');
    const [loading, setLoading] = useState(false);
    const [selectedSample, setSelectedSample] = useState<Sample | null>(null);
    const [selectedSampleId, setSelectedSampleId] = useState<string | null>(null);
    const [analysisStatus, setAnalysisStatus] = useState<QCAnalysisStatus>('not_started');
    const [qcProgress, setQcProgress] = useState<QCProgressData | null>(null);
    const [sampleStats, setSampleStats] = useState<SampleStatistics | null>(null);
    const [moduleStats, setModuleStats] = useState<ModuleStatistics | null>(null);

    // ========================================
    // WebSocket Integration
    // ========================================

    const {
        isConnected: wsConnected,
        connectionId: wsConnectionId,
        lastError: wsError,
        progressData: wsProgressData,
        disconnect: wsDisconnect,
        reconnect: wsReconnect
    } = useWebSocket({
        workbenchId: workbench.id,
        taskType: 'qc',
        enabled: true,
        onProgressUpdate: (data) => {
            // Handle QC progress updates
            if (data?.data) {
                const progressData = data.data as QCProgressData;
                setQcProgress(progressData);

                // Auto transition based on progress updates
                if (progressData.completed_files === progressData.total_files && progressData.total_files > 0) {
                    setAnalysisStatus('completing');
                    // Results will be loaded by fetchQCProgress when status changes to completing
                } else if (progressData.total_files > 0) {
                    // QC가 시작되면 즉시 running 상태로 전환 (completed_files = 0이어도)
                    setAnalysisStatus('running');
                }
            }
        },
        onConnect: () => {
            setWsStatus('connected');
        },
        onDisconnect: () => {
            setWsStatus('closed');
        },
        onError: (error) => {
            setWsStatus('error');
        }
    });

    // ========================================
    // Data Fetching Functions
    // ========================================

    /**
     * Fetch QC progress from API and conditionally load results
     */
    const fetchQCProgress = async () => {
        const shouldShowLoading = analysisStatus === 'not_started';

        try {
            // Only show loading for initial data fetch
            if (shouldShowLoading) {
                setLoading(true);
            }

            const response = await fetch(`/api/workbenches/${workbench.id}/qc-progress`, {
                credentials: 'include'
            });

            if (response.ok) {
                const data = await response.json();

                if (data.status) {
                    setAnalysisStatus(data.status);

                    // Only fetch results if QC is completing or completed
                    if (data.status === 'completing' || data.status === 'completed') {
                        await fetchQCResults();
                    }
                }
                if (data.progress_data) {
                    setQcProgress(data.progress_data);
                }
            }
        } catch (error) {
            console.error('Error fetching QC progress:', error);
        } finally {
            // Only clear loading if we set it (for initial fetch)
            if (shouldShowLoading) {
                setLoading(false);
            }
        }
    };

    /**
     * Fetch QC results from API
     */
    const fetchQCResults = async () => {
        try {
            setLoading(true);
            const response = await fetch(`/api/workbenches/${workbench.id}/qc/results`, {
                credentials: 'include'
            });

            if (response.ok) {
                const data: QCResultsResponse = await response.json();
                // Transform samples data if needed
                const samples: Sample[] = data.samples || [];
                setSamples(samples);

                // Store statistics data
                setSampleStats(data.sample_statistics || null);
                setModuleStats(data.module_statistics || null);

                if (samples.length > 0) {
                    setSelectedSample(null); // Start with overview
                }
            } else {
                console.error('Failed to fetch QC results');
                setSamples([]);
            }
        } catch (error) {
            console.error('Error fetching QC results:', error);
            setSamples([]);
        } finally {
            setLoading(false);
        }
    };

    // ========================================
    // Effects
    // ========================================

    /**
     * Load initial QC status (results loaded conditionally based on status)
     * Improved: Only fetch if no data exists to prevent unnecessary API calls on tab navigation
     */
    useEffect(() => {
        if (workbench?.id && samples.length === 0 && analysisStatus === 'not_started') {
            // Only load initial QC progress if we don't have data yet
            fetchQCProgress();
        }
    }, [workbench.id, samples.length, analysisStatus]);

    /**
     * Handle analysis status changes
     */
    useEffect(() => {
        if (analysisStatus === 'completing') {
            // Load QC results when transitioning to completing state
            fetchQCResults();

            // Auto-transition to completed after 3.5 seconds
            const timer = setTimeout(() => {
                setAnalysisStatus('completed');
            }, 3500); // 3.5 seconds for user to see completion message

            return () => clearTimeout(timer);
        }
    }, [analysisStatus]);


    /**
     * Generate per-base quality data for chart
     */
    const perBaseQualityData = React.useMemo(() => {
        if (qcData.length === 0) return [];

        // Generate data for positions 1-151
        return Array.from({ length: 151 }, (_, i) => ({
            position: i + 1,
            quality: Math.floor(Math.random() * 5) + 32, // Random quality between 32-37
            threshold_good: 28,
            threshold_poor: 20
        }));
    }, [qcData]);

    /**
     * Calculate QC statistics from backend data or samples data fallback
     * Uses module-level statistics from backend when available for more detailed view
     */
    const qcStats = React.useMemo(() => {
        // Use backend-calculated module statistics if available
        if (moduleStats && sampleStats) {
            return {
                // Sample-level stats
                total_samples: sampleStats.total_samples,
                passed_samples: sampleStats.passed_samples,
                warning_samples: sampleStats.warning_samples,
                failed_samples: sampleStats.failed_samples,

                // Module-level stats (the detailed view user requested)
                total_modules: moduleStats.total_modules,
                passed_modules: moduleStats.passed_modules,
                warning_modules: moduleStats.warning_modules,
                failed_modules: moduleStats.failed_modules
            };
        }

        // Fallback: Calculate from samples data if backend stats not available
        if (!samples.length) {
            return {
                total_samples: 0, passed_samples: 0, warning_samples: 0, failed_samples: 0,
                total_modules: 0, passed_modules: 0, warning_modules: 0, failed_modules: 0
            };
        }

        const sampleLevelStats = samples.reduce((stats, sample) => {
            stats.total_samples++;
            switch (sample.qc_status) {
                case 'passed': stats.passed_samples++; break;
                case 'warning': stats.warning_samples++; break;
                case 'failed': stats.failed_samples++; break;
                default: stats.failed_samples++; break;
            }
            return stats;
        }, { total_samples: 0, passed_samples: 0, warning_samples: 0, failed_samples: 0 });

        // For fallback, we don't have module-level data, so return zeros
        return {
            ...sampleLevelStats,
            total_modules: 0, passed_modules: 0, warning_modules: 0, failed_modules: 0
        };
    }, [samples, sampleStats, moduleStats]);

    // ========================================
    // Render
    // ========================================

    if (workbench.source_mode === 'existing_workbench' || workbench.source_mode === 'matrix_files') {
        return (
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="text-lg font-semibold text-slate-800">Quality Control</h3>
                <p className="mt-2 text-sm text-slate-600">
                    This workbench was created from imported matrices. Raw-read QC is not available for imported-matrix workflows.
                </p>
            </div>
        );
    }

    // If QC step is not enabled, show disabled message
    if (!isQCEnabled) {
        return (
            <div className="h-full flex items-center justify-center p-6">
                <div className="max-w-2xl w-full bg-slate-50 border-2 border-slate-200 rounded-xl p-8">
                    <div className="flex items-start">
                        <svg className="w-12 h-12 text-slate-400 mr-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                        </svg>
                        <div className="flex-1">
                            <h3 className="text-xl font-bold text-slate-800 mb-3">
                                This analysis step is disabled
                            </h3>
                            <div className="space-y-3 text-slate-700">
                                <p className="text-base">
                                    Quality Control (QC) step was not selected during workbench creation.
                                </p>
                                <div className="mt-4 pt-4 border-t border-slate-300">
                                    <p className="text-sm text-slate-600">
                                        This step is optional and has been skipped. You can create a new workbench with QC enabled if needed.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="text-center">
                    <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
                    <p className="text-slate-600">Loading QC results...</p>
                </div>
            </div>
        );
    }

    // Render different UI based on analysis status
    // 1. Not started or pending state - waiting for data download
    if (analysisStatus === 'not_started' || analysisStatus === 'pending') {
        return (
            <div className="space-y-6">
                {/* QC Dashboard Header */}
                <div className="bg-gradient-to-br from-gray-50 via-slate-50 to-gray-50 rounded-xl p-6 border border-gray-200">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center space-x-3">
                            <span className="text-3xl">⏳</span>
                            <h3 className="text-xl font-semibold text-slate-800">
                                Quality Control Analysis (FastQC) - {analysisStatus === 'pending' ? 'Pending' : 'Waiting'}
                            </h3>
                        </div>

                        {/* WebSocket Connection Status */}
                        <div className="flex items-center space-x-2 text-sm">
                            <div className={`w-2 h-2 rounded-full ${
                                wsStatus === 'connected' ? 'bg-green-500 animate-pulse' :
                                wsStatus === 'connecting' ? 'bg-yellow-500 animate-spin' :
                                wsStatus === 'error' ? 'bg-red-500' : 'bg-gray-400'
                            }`}></div>
                            <span className={`font-medium ${
                                wsStatus === 'connected' ? 'text-green-700' :
                                wsStatus === 'connecting' ? 'text-yellow-700' :
                                wsStatus === 'error' ? 'text-red-700' : 'text-gray-600'
                            }`}>
                                {wsStatus === 'connected' && '🟢 Live Updates'}
                                {wsStatus === 'connecting' && '🟡 Connecting...'}
                                {wsStatus === 'error' && '🔴 Connection Error'}
                                {wsStatus === 'closed' && '⚫ Not Connected'}
                            </span>
                        </div>
                    </div>
                </div>

                {/* Waiting Message */}
                <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-8">
                    <div className="text-center">
                        <div className="w-16 h-16 mx-auto mb-4 bg-blue-100 rounded-full flex items-center justify-center">
                            <span className="text-2xl">📥</span>
                        </div>
                        <h4 className="text-lg font-semibold text-slate-800 mb-2">
                            Waiting for Data Download to Complete
                        </h4>
                        <p className="text-slate-600 mb-4">
                            Quality control analysis will start automatically once all data files are downloaded and available.
                        </p>
                        <div className="flex items-center justify-center space-x-2 text-sm text-slate-500">
                            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                            <span>Please wait for the download step to complete...</span>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    // 2. Running state - show progress
    if (analysisStatus === 'running') {
        return (
            <div className="space-y-6">
                {/* QC Dashboard Header */}
                <div className="bg-gradient-to-br from-cyan-50 via-blue-50 to-indigo-50 rounded-xl p-6 border border-blue-200">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center space-x-3">
                            <span className="text-3xl">🔬</span>
                            <h3 className="text-xl font-semibold text-slate-800">
                                Quality Control Analysis (FastQC) - Running
                            </h3>
                        </div>

                        {/* WebSocket Connection Status */}
                        <div className="flex items-center space-x-2 text-sm">
                            <div className={`w-2 h-2 rounded-full ${
                                wsStatus === 'connected' ? 'bg-green-500 animate-pulse' :
                                wsStatus === 'connecting' ? 'bg-yellow-500 animate-spin' :
                                wsStatus === 'error' ? 'bg-red-500' : 'bg-gray-400'
                            }`}></div>
                            <span className={`font-medium ${
                                wsStatus === 'connected' ? 'text-green-700' :
                                wsStatus === 'connecting' ? 'text-yellow-700' :
                                wsStatus === 'error' ? 'text-red-700' : 'text-gray-600'
                            }`}>
                                {wsStatus === 'connected' && '🟢 Live Updates'}
                                {wsStatus === 'connecting' && '🟡 Connecting...'}
                                {wsStatus === 'error' && '🔴 Connection Error'}
                                {wsStatus === 'closed' && '⚫ Not Connected'}
                            </span>
                        </div>
                    </div>
                </div>

                {/* Progress View */}
                <QCProgressView progress={qcProgress} />
            </div>
        );
    }

    // 3. Completing state - show completion celebration
    if (analysisStatus === 'completing') {
        return (
            <div className="space-y-6">
                {/* QC Dashboard Header */}
                <div className="bg-gradient-to-br from-green-50 via-emerald-50 to-teal-50 rounded-xl p-6 border border-green-200">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center space-x-3">
                            <span className="text-3xl">🎉</span>
                            <h3 className="text-xl font-semibold text-green-800">
                                Quality Control Analysis (FastQC) - Complete!
                            </h3>
                        </div>

                        {/* WebSocket Connection Status */}
                        <div className="flex items-center space-x-2 text-sm">
                            <div className={`w-2 h-2 rounded-full ${
                                wsStatus === 'connected' ? 'bg-green-500 animate-pulse' :
                                wsStatus === 'connecting' ? 'bg-yellow-500 animate-spin' :
                                wsStatus === 'error' ? 'bg-red-500' : 'bg-gray-400'
                            }`}></div>
                            <span className={`font-medium ${
                                wsStatus === 'connected' ? 'text-green-700' :
                                wsStatus === 'connecting' ? 'text-yellow-700' :
                                wsStatus === 'error' ? 'text-red-700' : 'text-gray-600'
                            }`}>
                                {wsStatus === 'connected' && '🟢 Live Updates'}
                                {wsStatus === 'connecting' && '🟡 Connecting...'}
                                {wsStatus === 'error' && '🔴 Connection Error'}
                                {wsStatus === 'closed' && '⚫ Not Connected'}
                            </span>
                        </div>
                    </div>
                </div>

                {/* Completion Celebration View */}
                <QCCompletionView progress={qcProgress} />
            </div>
        );
    }

    // 4. Completed state - show results
    if (analysisStatus === 'completed' && samples.length > 0) {
        // Handle sample selection
        const handleSelectSample = (sampleId: string | null) => {
            setSelectedSampleId(sampleId);
            if (sampleId) {
                const sample = samples.find(s => s.id === sampleId);
                setSelectedSample(sample || null);
            } else {
                setSelectedSample(null);
            }
        };

        const handleSelectSampleFromOverview = (sample: Sample) => {
            setSelectedSample(sample);
            setSelectedSampleId(sample.id);
        };

        return (
            <div className="flex h-full">
                {/* Sidebar */}
                <QCSidebar
                    samples={samples}
                    selectedSampleId={selectedSampleId}
                    onSelectSample={handleSelectSample}
                />

                {/* Main Content Area */}
                <main className="flex-1 overflow-y-auto bg-white">
                    {selectedSample ? (
                        <QCSampleDetail sample={selectedSample} />
                    ) : (
                        <QCSampleOverview samples={samples} onSelectSample={handleSelectSampleFromOverview} moduleStatistics={moduleStats} />
                    )}
                </main>
            </div>
        );
    }

    // 5. Default state - show existing results or mock data
    return (
        <div className="space-y-6">
            {/* QC Dashboard Header */}
            <div className="bg-gradient-to-br from-cyan-50 via-blue-50 to-indigo-50 rounded-xl p-6 border border-blue-200">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center space-x-3">
                        <span className="text-3xl">🔬</span>
                        <h3 className="text-xl font-semibold text-slate-800">
                            Quality Control Analysis (FastQC)
                            {analysisStatus === 'completed' && ' - Completed ✅'}
                            {analysisStatus === 'not_started' && ' - Not Started'}
                        </h3>
                    </div>

                    {/* WebSocket Connection Status */}
                    <div className="flex items-center space-x-2 text-sm">
                        <div className={`w-2 h-2 rounded-full ${
                            wsStatus === 'connected' ? 'bg-green-500 animate-pulse' :
                            wsStatus === 'connecting' ? 'bg-yellow-500 animate-spin' :
                            wsStatus === 'error' ? 'bg-red-500' : 'bg-gray-400'
                        }`}></div>
                        <span className={`font-medium ${
                            wsStatus === 'connected' ? 'text-green-700' :
                            wsStatus === 'connecting' ? 'text-yellow-700' :
                            wsStatus === 'error' ? 'text-red-700' : 'text-gray-600'
                        }`}>
                            {wsStatus === 'connected' && '🟢 Live Updates'}
                            {wsStatus === 'connecting' && '🟡 Connecting...'}
                            {wsStatus === 'error' && '🔴 Connection Error'}
                            {wsStatus === 'closed' && '⚫ Not Connected'}
                        </span>
                    </div>
                </div>

                {/* QC Module-Level Statistics */}
                <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-6 border border-blue-200 mb-6">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center space-x-3">
                            <span className="text-2xl">📊</span>
                            <h4 className="text-lg font-semibold text-slate-800">FastQC Module Statistics</h4>
                        </div>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-center">
                        <div className="bg-white rounded-lg p-4 border border-slate-200">
                            <div className="text-2xl font-bold text-slate-600">{qcStats.total_samples}</div>
                            <div className="text-sm text-slate-500 mt-1">Samples</div>
                        </div>
                        <div className="bg-white rounded-lg p-4 border border-slate-200">
                            <div className="text-2xl font-bold text-blue-600">{qcStats.total_modules}</div>
                            <div className="text-sm text-slate-500 mt-1">Total Modules</div>
                        </div>
                        <div className="bg-white rounded-lg p-4 border border-slate-200">
                            <div className="text-2xl font-bold text-green-600">{qcStats.passed_modules}</div>
                            <div className="text-sm text-slate-500 mt-1">Passed Modules</div>
                        </div>
                        <div className="bg-white rounded-lg p-4 border border-slate-200">
                            <div className="text-2xl font-bold text-yellow-600">{qcStats.warning_modules}</div>
                            <div className="text-sm text-slate-500 mt-1">Warning Modules</div>
                        </div>
                        <div className="bg-white rounded-lg p-4 border border-slate-200">
                            <div className="text-2xl font-bold text-red-600">{qcStats.failed_modules}</div>
                            <div className="text-sm text-slate-500 mt-1">Failed Modules</div>
                        </div>
                    </div>
                    <div className="mt-4 text-center">
                        <p className="text-sm text-slate-600">
                            <strong>Summary:</strong> Samples: {qcStats.total_samples} |
                            Total Modules: {qcStats.total_modules} |
                            Passed Modules: {qcStats.passed_modules} |
                            Warning Modules: {qcStats.warning_modules} |
                            Failed Modules: {qcStats.failed_modules}
                        </p>
                    </div>
                </div>

                {/* QC Sample-Level Statistics */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                    <QualityScoreCard
                        title="Total Samples"
                        value={qcStats.total_samples}
                        unit=""
                        color="text-slate-600"
                    />
                    <QualityScoreCard
                        title="Passed Samples"
                        value={qcStats.passed_samples}
                        unit=""
                        color="text-green-600"
                    />
                    <QualityScoreCard
                        title="Warning Samples"
                        value={qcStats.warning_samples}
                        unit=""
                        color="text-yellow-600"
                    />
                    <QualityScoreCard
                        title="Failed Samples"
                        value={qcStats.failed_samples}
                        unit=""
                        color="text-red-600"
                    />
                </div>

                {/* QC Summary Statistics */}
                <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
                    <QualityScoreCard
                        title="Avg Quality Score"
                        value={35.2}
                        unit=""
                        color="text-green-600"
                    />
                    <QualityScoreCard
                        title="Total Sequences"
                        value="42.5"
                        unit="M"
                        color="text-blue-600"
                    />
                    <QualityScoreCard
                        title="Avg GC Content"
                        value={48}
                        unit="%"
                        color="text-purple-600"
                    />
                    <QualityScoreCard
                        title="Sequence Length"
                        value="50-151"
                        unit=""
                        color="text-indigo-600"
                    />
                    <QualityScoreCard
                        title="Duplication Rate"
                        value={15.3}
                        unit="%"
                        color="text-yellow-600"
                    />
                    <QualityScoreCard
                        title="Adapter Content"
                        value={2.1}
                        unit="%"
                        color="text-red-600"
                    />
                </div>
            </div>

            {/* Quality Charts Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Per Base Quality Chart */}
                <PerBaseQualityChart data={perBaseQualityData} />

                {/* GC Content Distribution */}
                <GCContentChart data={qcData} />

                {/* QC Status Summary */}
                {qcResults.length > 0 && (
                    <QualityStatusSummary qcResults={qcResults} />
                )}

                {/* Sequence Duplication Levels */}
                <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
                    <h4 className="text-lg font-semibold text-slate-800 mb-4">Sequence Duplication Levels</h4>
                    <ResponsiveContainer width="100%" height={250}>
                        <LineChart data={qcData.map(d => ({
                            sample: d.sample_name,
                            duplication: d.duplication_level
                        }))}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                            <XAxis dataKey="sample" stroke="#64748b" />
                            <YAxis
                                label={{ value: 'Duplication Level (%)', angle: -90, position: 'insideLeft' }}
                                stroke="#64748b"
                            />
                            <Tooltip
                                contentStyle={{
                                    backgroundColor: '#ffffff',
                                    border: '1px solid #e2e8f0',
                                    borderRadius: '8px'
                                }}
                            />
                            <Line type="monotone" dataKey="duplication" stroke="#f59e0b" strokeWidth={2} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Sample Details Table */}
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm">
                <div className="p-6 border-b border-slate-200">
                    <h4 className="text-lg font-semibold text-slate-800">Sample Quality Details</h4>
                </div>
                <div className="overflow-x-auto">
                    <table className="min-w-full">
                        <thead className="bg-slate-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-sm font-medium text-slate-700">Sample</th>
                                <th className="px-6 py-3 text-left text-sm font-medium text-slate-700">Total Sequences</th>
                                <th className="px-6 py-3 text-left text-sm font-medium text-slate-700">GC Content</th>
                                <th className="px-6 py-3 text-left text-sm font-medium text-slate-700">Quality Score</th>
                                <th className="px-6 py-3 text-left text-sm font-medium text-slate-700">Status</th>
                                <th className="px-6 py-3 text-left text-sm font-medium text-slate-700">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200">
                            {qcData.map((sample) => (
                                <tr key={sample.sample_id} className="hover:bg-slate-50 transition-colors">
                                    <td className="px-6 py-4 text-sm font-medium text-slate-900">
                                        {sample.sample_name}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-slate-600">
                                        {(sample.total_sequences / 1000000).toFixed(1)}M
                                    </td>
                                    <td className="px-6 py-4 text-sm text-slate-600">
                                        {sample.gc_content}%
                                    </td>
                                    <td className="px-6 py-4 text-sm">
                                        <span className="px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800">
                                            Good (35)
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-sm">
                                        <span className="flex items-center space-x-1">
                                            <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                                            <span className="text-slate-600">Passed</span>
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-sm">
                                        <button
                                            className="text-blue-600 hover:text-blue-800 font-medium"
                                            onClick={() => setSelectedSample(sample.sample_id)}
                                        >
                                            View Report
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* MultiQC Report Link */}
            <div className="bg-gradient-to-r from-emerald-50 to-teal-50 rounded-xl p-6 border border-emerald-200">
                <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                        <span className="text-2xl">📊</span>
                        <div>
                            <h4 className="text-lg font-semibold text-slate-800">MultiQC Report</h4>
                            <p className="text-sm text-slate-600 mt-1">
                                Aggregated quality control report for all samples
                            </p>
                        </div>
                    </div>
                    <button className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors flex items-center space-x-2">
                        <span>View MultiQC Report</span>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    );
};

export default WorkbenchDetailQC;
