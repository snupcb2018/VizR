import React, { useState, useEffect } from 'react';
import useWebSocket from '../src/hooks/useWebSocket';
import { Workbench, StepDetail } from '../types';

// ========================================
// Type Definitions
// ========================================

interface PreprocessingProgressData {
    completed_files: number;
    total_files: number;
    progress_percent: number;
}

interface ToolProgressResponse {
    workbench_id: number;
    status: 'not_started' | 'pending' | 'running' | 'completed' | 'failed';
    progress_data: PreprocessingProgressData | null;
    last_updated: string | null;
}

interface TrimmomaticResultsResponse {
    workbench_id: number;
    samples: Array<{
        sample_name: string;
        input_reads: number;
        surviving_reads: number;
        survival_rate: number;
        adapter_removed: number;
    }>;
    total_count: number;
    summary: {
        total_input_reads: number;
        total_surviving_reads: number;
        average_survival_rate: number;
        total_removed: number;
    };
}

interface WorkbenchDetailPreprocessingTrimmomaticProps {
    workbench: Workbench;
    pipelineStepsData: StepDetail[];
}

// ========================================
// Component Definitions
// ========================================

const ProgressBar = ({ progress }: { progress: PreprocessingProgressData | null }) => {
    if (!progress) {
        return (
            <div className="w-full bg-slate-200 rounded-full h-2">
                <div className="bg-slate-400 h-2 rounded-full w-0"></div>
            </div>
        );
    }

    const percentage = Math.min(100, Math.max(0, progress.progress_percent || 0));

    return (
        <div className="w-full">
            <div className="flex justify-between text-sm text-slate-600 mb-2">
                <span>Trimmomatic Progress</span>
                <span>{progress.completed_files}/{progress.total_files} files ({percentage.toFixed(1)}%)</span>
            </div>
            <div className="w-full bg-slate-200 rounded-full h-2">
                <div
                    className="bg-blue-600 h-2 rounded-full transition-all duration-300 ease-out"
                    style={{ width: `${percentage}%` }}
                ></div>
            </div>
        </div>
    );
};

const StatusBadge = ({ status }: { status: string }) => {
    const statusConfig = {
        'not_started': { color: 'bg-slate-100 text-slate-600', text: 'Not Started' },
        'pending': { color: 'bg-yellow-100 text-yellow-700', text: 'Pending' },
        'running': { color: 'bg-blue-100 text-blue-700', text: 'Running' },
        'completed': { color: 'bg-green-100 text-green-700', text: 'Completed' },
        'failed': { color: 'bg-red-100 text-red-700', text: 'Failed' }
    };

    const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.not_started;

    return (
        <span className={`px-2 py-1 rounded-full text-xs font-medium ${config.color}`}>
            {config.text}
        </span>
    );
};

// ========================================
// Main Component
// ========================================

const WorkbenchDetailPreprocessingTrimmomatic: React.FC<WorkbenchDetailPreprocessingTrimmomaticProps> = ({
    workbench,
    pipelineStepsData
}) => {
    // ========================================
    // Check if Trimmomatic is enabled
    // ========================================
    const isTrimmomaticEnabled = pipelineStepsData.some(step =>
        step.step === 'clean' &&
        step.parameters?.clean_tools?.includes('trimmomatic')
    );

    const [progressData, setProgressData] = useState<ToolProgressResponse | null>(null);
    const [results, setResults] = useState<TrimmomaticResultsResponse | null>(null);
    const [loading, setLoading] = useState(false);

    // WebSocket connection for real-time progress updates
    const {
        isConnected: wsIsConnected,
        connectionId: wsConnectionId,
        lastError: wsLastError,
        progressData: wsProgressData,
        disconnect: wsDisconnect,
        reconnect: wsReconnect
    } = useWebSocket({
        workbenchId: workbench.id,
        taskType: 'trimmomatic',
        enabled: true,
        onProgressUpdate: (data) => {
            // Update progress data when WebSocket receives updates
            if (data && typeof data === 'object') {
                const progressInfo = data.data || data;
                const progressPercent = progressInfo.progress_percent || 0;
                const isCompleted = progressPercent >= 100;
                const newStatus = isCompleted ? 'completed' : 'running';

                setProgressData(prev => {
                    return {
                        ...prev,
                        workbench_id: workbench.id,
                        status: newStatus,
                        progress_data: {
                            completed_files: progressInfo.completed_files || 0,
                            total_files: progressInfo.total_files || 0,
                            progress_percent: progressPercent
                        },
                        last_updated: new Date().toISOString()
                    };
                });
            }
        },
        onConnect: () => {
            // WebSocket connected for Trimmomatic
        },
        onDisconnect: () => {
            // WebSocket disconnected for Trimmomatic
        },
        onError: (error) => {
            // WebSocket error for Trimmomatic
        }
    });

    /**
     * Fetch Trimmomatic progress from API
     */
    const fetchProgress = async () => {
        if (loading) return;
        setLoading(true);

        try {
            const response = await fetch(`/api/workbenches/${workbench.id}/trimmomatic-progress`, {
                credentials: 'include'
            });

            if (response.ok) {
                const data: ToolProgressResponse = await response.json();
                setProgressData(data);
            }
        } catch (error) {
            // Error fetching progress
        } finally {
            setLoading(false);
        }
    };

    /**
     * Fetch Trimmomatic results from API
     */
    const fetchResults = async () => {
        try {
            const response = await fetch(`/api/workbenches/${workbench.id}/trimmomatic-results`, {
                credentials: 'include'
            });

            if (response.ok) {
                const data: TrimmomaticResultsResponse = await response.json();
                setResults(data);
            }
        } catch (error) {
            // Error fetching results
        }
    };

    // Fetch data once when component mounts
    useEffect(() => {
        fetchProgress();
    }, []);

    // Fetch results if completed
    useEffect(() => {
        if (progressData?.status === 'completed') {
            fetchResults();
        }
    }, [progressData?.status]);

    const status = progressData?.status || 'not_started';

    // If Trimmomatic is not enabled, show disabled message
    if (!isTrimmomaticEnabled) {
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
                                    Trimmomatic preprocessing step was not selected during workbench creation.
                                </p>
                                <div className="mt-4 pt-4 border-t border-slate-300">
                                    <p className="text-sm text-slate-600">
                                        This step is optional and has been skipped. You can create a new workbench with Trimmomatic enabled if needed.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="h-full p-6">
            <div className="bg-white rounded-lg shadow-sm border border-slate-200">
                <div className="p-6">
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center space-x-4">
                            <h3 className="text-lg font-semibold text-slate-900">Trimmomatic Sequence Preprocessing</h3>
                            {/* WebSocket Connection Indicator */}
                            <div className="flex items-center space-x-2">
                                <div className={`w-2 h-2 rounded-full ${
                                    wsIsConnected ? 'bg-green-500' : 'bg-red-500'
                                }`} />
                                <span className="text-xs text-slate-500">
                                    {wsIsConnected ? 'Live' : 'Offline'}
                                </span>
                                {!wsIsConnected && (
                                    <button
                                        onClick={wsReconnect}
                                        className="text-xs text-blue-600 hover:text-blue-800 underline"
                                    >
                                        Reconnect
                                    </button>
                                )}
                            </div>
                        </div>
                        <StatusBadge status={status} />
                    </div>

                    {/* Progress Section */}
                    <div className="mb-6">
                        <ProgressBar progress={progressData?.progress_data || null} />

                        {/* WebSocket Status and Loading Indicators */}
                        <div className="mt-2 flex items-center justify-between text-sm text-slate-500">
                            <div className="flex items-center space-x-4">
                                {loading && (
                                    <span className="animate-pulse">Loading progress...</span>
                                )}
                                {wsLastError && (
                                    <span className="text-red-500">
                                        Connection error: {wsLastError}
                                    </span>
                                )}
                            </div>

                            {progressData?.last_updated && (
                                <span className="text-xs">
                                    Updated: {new Date(progressData.last_updated).toLocaleTimeString()}
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Results Section */}
                    {status === 'completed' && results ? (
                        <div>
                            <div className="flex items-center justify-between mb-4">
                                <h4 className="text-md font-semibold text-slate-800">Processing Results</h4>
                                <span className="text-xs text-slate-500">
                                    {results.samples.length} sample{results.samples.length !== 1 ? 's' : ''} processed
                                </span>
                            </div>

                            {/* Summary Statistics */}
                            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                                <div className="bg-slate-50 rounded-lg p-4">
                                    <div className="text-sm font-medium text-slate-500">Total Samples</div>
                                    <div className="text-2xl font-bold text-slate-900">{results.total_count}</div>
                                </div>
                                <div className="bg-blue-50 rounded-lg p-4">
                                    <div className="text-sm font-medium text-blue-600">Input Reads</div>
                                    <div className="text-2xl font-bold text-blue-900">{results.summary.total_input_reads.toLocaleString()}</div>
                                </div>
                                <div className="bg-green-50 rounded-lg p-4">
                                    <div className="text-sm font-medium text-green-600">Surviving Reads</div>
                                    <div className="text-2xl font-bold text-green-900">{results.summary.total_surviving_reads.toLocaleString()}</div>
                                </div>
                                <div className="bg-yellow-50 rounded-lg p-4">
                                    <div className="text-sm font-medium text-yellow-600">Survival Rate</div>
                                    <div className="text-2xl font-bold text-yellow-900">{results.summary.average_survival_rate.toFixed(1)}%</div>
                                </div>
                            </div>

                            {/* Sample Results Cards */}
                            {results.samples.length > 0 ? (
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    {results.samples.map((sample, index) => (
                                        <div key={index} className="bg-white border border-slate-200 rounded-lg p-4 hover:shadow-md transition-shadow">
                                            {/* Sample Header */}
                                            <div className="flex items-center justify-between mb-3">
                                                <h5 className="text-sm font-semibold text-slate-900 truncate">
                                                    {sample.sample_name}
                                                </h5>
                                                <span className={`px-2 py-1 rounded text-xs font-medium ${
                                                    sample.survival_rate >= 90
                                                        ? 'bg-green-100 text-green-700'
                                                        : sample.survival_rate >= 80
                                                            ? 'bg-yellow-100 text-yellow-700'
                                                            : 'bg-red-100 text-red-700'
                                                }`}>
                                                    {sample.survival_rate.toFixed(1)}%
                                                </span>
                                            </div>

                                            {/* Sample Metrics */}
                                            <div className="space-y-2">
                                                <div className="flex justify-between items-center">
                                                    <span className="text-xs text-slate-500">Input Reads</span>
                                                    <span className="text-sm font-medium text-slate-900">
                                                        {sample.input_reads.toLocaleString()}
                                                    </span>
                                                </div>

                                                <div className="flex justify-between items-center">
                                                    <span className="text-xs text-slate-500">Surviving</span>
                                                    <span className="text-sm font-medium text-green-600">
                                                        {sample.surviving_reads.toLocaleString()}
                                                    </span>
                                                </div>

                                                <div className="flex justify-between items-center">
                                                    <span className="text-xs text-slate-500">Removed</span>
                                                    <span className="text-sm font-medium text-red-600">
                                                        {sample.adapter_removed.toLocaleString()}
                                                    </span>
                                                </div>
                                            </div>

                                            {/* Visual Progress Bar */}
                                            <div className="mt-3">
                                                <div className="w-full bg-slate-200 rounded-full h-2">
                                                    <div
                                                        className={`h-2 rounded-full transition-all duration-300 ${
                                                            sample.survival_rate >= 90
                                                                ? 'bg-green-500'
                                                                : sample.survival_rate >= 80
                                                                    ? 'bg-yellow-500'
                                                                    : 'bg-red-500'
                                                        }`}
                                                        style={{ width: `${sample.survival_rate}%` }}
                                                    ></div>
                                                </div>
                                                <div className="flex justify-between text-xs text-slate-400 mt-1">
                                                    <span>0%</span>
                                                    <span>100%</span>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <p className="text-slate-500 text-center py-8">No results available yet</p>
                            )}
                        </div>
                    ) : (
                        <div className="text-center py-12">
                            <div className="text-slate-400 mb-4">
                                <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                                </svg>
                            </div>
                            <h4 className="text-lg font-medium text-slate-900 mb-2">
                                {status === 'running' ? 'Processing...' : 'Waiting for Processing'}
                            </h4>
                            <p className="text-slate-500">
                                {status === 'running'
                                    ? 'Trimmomatic is currently processing your sequences'
                                    : 'Trimmomatic processing will begin once initiated'
                                }
                            </p>
                            {status === 'running' && !wsIsConnected && (
                                <div className="mt-4 flex items-center space-x-3">
                                    <button
                                        onClick={fetchProgress}
                                        disabled={loading}
                                        className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                                    >
                                        {loading ? 'Refreshing...' : 'Refresh Progress'}
                                    </button>
                                    <button
                                        onClick={wsReconnect}
                                        className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
                                    >
                                        Connect Live Updates
                                    </button>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default WorkbenchDetailPreprocessingTrimmomatic;