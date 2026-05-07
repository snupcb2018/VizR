import React, { useState, useEffect } from 'react';
import useWebSocket from '../src/hooks/useWebSocket';
import { Workbench, StepDetail } from '../types';

// ========================================
// Type Definitions
// ========================================

interface AlignmentProgressData {
    completed_files: number;
    total_files: number;
    progress_percent: number;
}

interface ToolProgressResponse {
    workbench_id: number;
    status: 'not_started' | 'pending' | 'running' | 'completed' | 'failed';
    progress_data: AlignmentProgressData | null;
    last_updated: string | null;
}

interface AlignmentResultsResponse {
    workbench_id: number;
    samples: Array<{
        sample_name: string;
        total_reads: number;
        mapped_reads: number;
        unmapped_reads: number;
        mapping_rate: number;
        multi_mapped_reads?: number;
        multi_mapping_rate?: number;
        parsing_successful: boolean;
    }>;
    total_count: number;
    summary: {
        total_reads: number;
        total_mapped_reads: number;
        total_unmapped_reads: number;
        average_mapping_rate: number;
        overall_mapping_rate: number;
    };
}

interface WorkbenchDetailAlignmentProps {
    workbench: Workbench;
    pipelineStepsData: StepDetail[];
}

// ========================================
// Component Definitions
// ========================================

const ProgressBar = ({ progress }: { progress: AlignmentProgressData | null }) => {
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
                <span>Alignment Progress</span>
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

const WorkbenchDetailAlignment: React.FC<WorkbenchDetailAlignmentProps> = ({
    workbench,
    pipelineStepsData
}) => {
    const [progressData, setProgressData] = useState<ToolProgressResponse | null>(null);
    const [results, setResults] = useState<AlignmentResultsResponse | null>(null);
    const [loading, setLoading] = useState(false);

    // Extract alignment tool name from pipeline steps data or progress data
    const alignmentStep = pipelineStepsData?.find(step =>
        step.step_name === 'alignment' ||
        step.step_name === 'align' ||
        step.tool_name?.toLowerCase().includes('hisat2') ||
        step.tool_name?.toLowerCase().includes('star') ||
        step.tool_name?.toLowerCase().includes('bowtie')
    );

    // Priority: API progress data tool_name > pipeline steps tool_name > fallback
    const toolName = progressData?.progress_data?.tool_name ||
                     alignmentStep?.tool_name ||
                     'Unknown';

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
        taskType: 'hisat2',
        enabled: true,
        onProgressUpdate: (data) => {
            // Update progress data when WebSocket receives updates
            if (data && typeof data === 'object') {
                // Extract progress data from nested structure
                const progressInfo = data.data || data;

                setProgressData(prev => {
                    const progressPercent = progressInfo.progress_percent || 0;
                    const isCompleted = progressPercent >= 100;
                    const newStatus = isCompleted ? 'completed' : 'running';

                    return {
                        ...prev,
                        workbench_id: workbench.id,
                        status: newStatus,
                        progress_data: {
                            completed_files: progressInfo.completed_samples || progressInfo.completed_files || 0,
                            total_files: progressInfo.total_samples || progressInfo.total_files || 0,
                            progress_percent: progressPercent
                        },
                        last_updated: new Date().toISOString()
                    };
                });
            }
        },
        onConnect: () => {
            // WebSocket connected
        },
        onDisconnect: () => {
            // WebSocket disconnected
        },
        onError: (error) => {
            // WebSocket error
        }
    });

    /**
     * Fetch Alignment progress from API
     */
    const fetchProgress = async () => {
        if (loading) return;
        setLoading(true);

        try {
            const response = await fetch(`/api/workbenches/${workbench.id}/alignment-progress`, {
                credentials: 'include'
            });

            if (response.ok) {
                const data: ToolProgressResponse = await response.json();
                setProgressData(data);
            }
        } catch (error) {
            // Error fetching alignment progress
        } finally {
            setLoading(false);
        }
    };

    /**
     * Fetch Alignment results from API
     */
    const fetchResults = async () => {
        try {
            const response = await fetch(`/api/workbenches/${workbench.id}/alignment-results`, {
                credentials: 'include'
            });

            if (response.ok) {
                const data: AlignmentResultsResponse = await response.json();
                setResults(data);
            }
        } catch (error) {
            // Error fetching alignment results
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

    if (workbench.source_mode === 'existing_workbench' || workbench.source_mode === 'matrix_files') {
        return (
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="text-lg font-semibold text-slate-800">Read Alignment</h3>
                <p className="mt-2 text-sm text-slate-600">
                    This workbench starts from imported matrices, so alignment is not applicable.
                </p>
            </div>
        );
    }

    return (
        <div className="h-full p-6">
            <div className="bg-white rounded-lg shadow-sm border border-slate-200">
                <div className="p-6">
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center space-x-4">
                            <h3 className="text-lg font-semibold text-slate-900">Read Alignment</h3>
                            {toolName && toolName !== 'Unknown' && (
                                <span className="px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-sm font-medium">
                                    {toolName.toUpperCase()}
                                </span>
                            )}
                            {/* WebSocket Connection Indicator */}
                            <div className="flex items-center space-x-2">
                                <div className={`w-2 h-2 rounded-full ${
                                    wsIsConnected ? 'bg-green-500' : 'bg-red-500'
                                }`} />
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
                                <h4 className="text-md font-semibold text-slate-800">Alignment Results</h4>
                                <span className="text-xs text-slate-500">
                                    {results.samples.length} sample{results.samples.length !== 1 ? 's' : ''} processed
                                </span>
                            </div>

                            {/* Summary Statistics */}
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                                <div className="bg-slate-50 rounded-lg p-4">
                                    <div className="text-sm font-medium text-slate-500">Overall Mapping Rate</div>
                                    <div className="text-2xl font-bold text-slate-900">
                                        {results.summary.overall_mapping_rate.toFixed(1)}%
                                    </div>
                                </div>
                                <div className="bg-blue-50 rounded-lg p-4">
                                    <div className="text-sm font-medium text-blue-600">Total Reads</div>
                                    <div className="text-2xl font-bold text-blue-900">
                                        {(results.summary.total_reads / 1000000).toFixed(1)}M
                                    </div>
                                </div>
                                <div className="bg-green-50 rounded-lg p-4">
                                    <div className="text-sm font-medium text-green-600">Mapped Reads</div>
                                    <div className="text-2xl font-bold text-green-900">
                                        {(results.summary.total_mapped_reads / 1000000).toFixed(1)}M
                                    </div>
                                </div>
                                <div className="bg-red-50 rounded-lg p-4">
                                    <div className="text-sm font-medium text-red-600">Unmapped Reads</div>
                                    <div className="text-2xl font-bold text-red-900">
                                        {(results.summary.total_unmapped_reads / 1000000).toFixed(1)}M
                                    </div>
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
                                                    sample.mapping_rate >= 90
                                                        ? 'bg-green-100 text-green-700'
                                                        : sample.mapping_rate >= 80
                                                            ? 'bg-yellow-100 text-yellow-700'
                                                            : 'bg-red-100 text-red-700'
                                                }`}>
                                                    {sample.mapping_rate.toFixed(1)}%
                                                </span>
                                            </div>

                                            {/* Sample Metrics */}
                                            <div className="space-y-2">
                                                <div className="flex justify-between items-center">
                                                    <span className="text-xs text-slate-500">Total Reads</span>
                                                    <span className="text-sm font-medium text-slate-900">
                                                        {sample.total_reads.toLocaleString()}
                                                    </span>
                                                </div>

                                                <div className="flex justify-between items-center">
                                                    <span className="text-xs text-slate-500">Mapped Reads</span>
                                                    <span className="text-sm font-medium text-green-600">
                                                        {sample.mapped_reads.toLocaleString()}
                                                    </span>
                                                </div>

                                                <div className="flex justify-between items-center">
                                                    <span className="text-xs text-slate-500">Unmapped Reads</span>
                                                    <span className="text-sm font-medium text-red-600">
                                                        {sample.unmapped_reads.toLocaleString()}
                                                    </span>
                                                </div>

                                                {sample.multi_mapped_reads !== undefined && sample.multi_mapped_reads !== null && (
                                                    <div className="flex justify-between items-center">
                                                        <span className="text-xs text-slate-500">Multi-mapped</span>
                                                        <span className="text-sm font-medium text-orange-600">
                                                            {sample.multi_mapped_reads.toLocaleString()}
                                                            {sample.multi_mapping_rate && ` (${sample.multi_mapping_rate.toFixed(1)}%)`}
                                                        </span>
                                                    </div>
                                                )}
                                            </div>

                                            {/* Visual Progress Bar */}
                                            <div className="mt-3">
                                                <div className="w-full bg-slate-200 rounded-full h-2">
                                                    <div
                                                        className={`h-2 rounded-full transition-all duration-300 ${
                                                            sample.mapping_rate >= 90
                                                                ? 'bg-green-500'
                                                                : sample.mapping_rate >= 80
                                                                    ? 'bg-yellow-500'
                                                                    : 'bg-red-500'
                                                        }`}
                                                        style={{ width: `${sample.mapping_rate}%` }}
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
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                                </svg>
                            </div>
                            <h4 className="text-lg font-medium text-slate-900 mb-2">
                                {status === 'running' ? 'Aligning Reads...' : 'Waiting for Alignment'}
                            </h4>
                            <p className="text-slate-500">
                                {status === 'running'
                                    ? `${toolName !== 'Unknown' ? toolName.toUpperCase() : 'Alignment tool'} is currently aligning your reads to the reference genome`
                                    : 'Read alignment will begin after sequence preprocessing completes'
                                }
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default WorkbenchDetailAlignment;
