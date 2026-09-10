import React, { useEffect, useState } from 'react';
import useWebSocket from '../src/hooks/useWebSocket';
import { Workbench, StepDetail } from '../types';
import {
    QCSidebar,
    QCSampleOverview,
    QCSampleDetail,
    Sample,
    QCResultsResponse,
    ModuleStatistics,
    QCResultError,
    QCResultStatus,
} from './qc';

type QCAnalysisStatus = 'not_started' | 'pending' | 'running' | 'completing' | 'completed' | 'failed' | 'cancelled';

interface QCProgressData {
    completed_files: number;
    total_files: number;
    progress_percent: number;
    successful_files?: number;
    failed_files?: number;
    displayable_files?: number;
    result_status?: QCResultStatus | 'processing';
    errors?: QCResultError[];
    last_updated?: number;
}

interface WorkbenchDetailQCProps {
    workbench: Workbench;
    pipelineStepsData: StepDetail[];
    executedStepNames: string[];
}

const wait = (milliseconds: number) => new Promise(resolve => setTimeout(resolve, milliseconds));

const WorkbenchDetailQC: React.FC<WorkbenchDetailQCProps> = ({
    workbench,
    executedStepNames,
}) => {
    const isQCEnabled = executedStepNames.includes('qc');
    const [samples, setSamples] = useState<Sample[]>([]);
    const [selectedSampleId, setSelectedSampleId] = useState<string | null>(null);
    const [analysisStatus, setAnalysisStatus] = useState<QCAnalysisStatus>('not_started');
    const [resultStatus, setResultStatus] = useState<QCResultStatus | 'processing'>('processing');
    const [qcProgress, setQcProgress] = useState<QCProgressData | null>(null);
    const [moduleStats, setModuleStats] = useState<ModuleStatistics | null>(null);
    const [resultErrors, setResultErrors] = useState<QCResultError[]>([]);
    const [resultCounts, setResultCounts] = useState({ expected: 0, parsed: 0, failed: 0 });
    const [initialLoading, setInitialLoading] = useState(true);
    const [retrying, setRetrying] = useState(false);
    const [fetchError, setFetchError] = useState<string | null>(null);

    const applyResults = (data: QCResultsResponse) => {
        const loadedSamples = data.samples || [];
        const resolvedStatus = data.result_status || (loadedSamples.length > 0 ? 'ready' : 'unavailable');
        setSamples(loadedSamples);
        setModuleStats(data.module_statistics || null);
        setResultStatus(resolvedStatus);
        setResultErrors(data.errors || []);
        setResultCounts({
            expected: data.expected_count ?? loadedSamples.length,
            parsed: data.parsed_count ?? loadedSamples.length,
            failed: data.failed_count ?? 0,
        });
        setSelectedSampleId(current => (
            current && loadedSamples.some(sample => sample.id === current) ? current : null
        ));
        setFetchError(null);
        return resolvedStatus;
    };

    const fetchQCResults = async (attempts = 1, cancelled: () => boolean = () => false) => {
        let lastError = 'QC results are not available.';
        for (let attempt = 0; attempt < attempts; attempt += 1) {
            try {
                const response = await fetch(`/api/workbenches/${workbench.id}/qc/results`, {
                    credentials: 'include',
                });
                if (!response.ok) {
                    let detail = '';
                    try {
                        const body = await response.json();
                        detail = body.error ? `: ${body.error}` : '';
                    } catch {
                        // Keep the status-based error when the response is not JSON.
                    }
                    throw new Error(`Unable to load QC results (${response.status})${detail}`);
                }

                const data: QCResultsResponse = await response.json();
                if (cancelled()) return null;
                const status = applyResults(data);
                if (status !== 'unavailable' || attempt === attempts - 1) return status;
            } catch (error) {
                lastError = error instanceof Error ? error.message : 'Unable to load QC results.';
                if (attempt === attempts - 1 && !cancelled()) {
                    setFetchError(lastError);
                }
            }
            if (attempt < attempts - 1) await wait(1000);
        }
        return null;
    };

    const retryResults = async () => {
        setRetrying(true);
        setFetchError(null);
        await fetchQCResults(5);
        setRetrying(false);
    };

    useWebSocket({
        workbenchId: workbench.id,
        taskType: 'qc',
        enabled: isQCEnabled,
        onProgressUpdate: (data) => {
            if (!data?.data) return;
            const progress = data.data as QCProgressData;
            setQcProgress(progress);
            setResultStatus(progress.result_status || 'processing');
            if (progress.errors) setResultErrors(progress.errors);
            setResultCounts({
                expected: progress.total_files || 0,
                parsed: progress.displayable_files || 0,
                failed: progress.failed_files || 0,
            });

            if (progress.result_status === 'unavailable') {
                setAnalysisStatus('failed');
            } else if (
                progress.total_files > 0
                && progress.completed_files === progress.total_files
                && (progress.result_status === 'ready' || progress.result_status === 'partial')
            ) {
                setAnalysisStatus('completing');
            } else if (progress.total_files > 0) {
                setAnalysisStatus('running');
            }
        },
    });

    useEffect(() => {
        let cancelled = false;
        setSamples([]);
        setSelectedSampleId(null);
        setAnalysisStatus('not_started');
        setResultStatus('processing');
        setQcProgress(null);
        setModuleStats(null);
        setResultErrors([]);
        setResultCounts({ expected: 0, parsed: 0, failed: 0 });
        setFetchError(null);
        setInitialLoading(true);

        const initialize = async () => {
            try {
                const response = await fetch(`/api/workbenches/${workbench.id}/qc-progress`, {
                    credentials: 'include',
                });
                if (!response.ok) throw new Error(`Unable to load QC status (${response.status})`);
                const data = await response.json();
                if (cancelled) return;
                const status = (data.status || 'not_started') as QCAnalysisStatus;
                setAnalysisStatus(status);
                setResultStatus(data.result_status || data.progress_data?.result_status || 'processing');
                setQcProgress(data.progress_data || null);
                if (data.progress_data?.errors) setResultErrors(data.progress_data.errors);

                if (status === 'completed' || status === 'failed' || status === 'cancelled') {
                    await fetchQCResults(5, () => cancelled);
                } else if (status === 'not_started' && isQCEnabled) {
                    // Legacy workbenches may have artifacts without a persisted QC step.
                    const discoveredStatus = await fetchQCResults(1, () => cancelled);
                    if (!cancelled && (discoveredStatus === 'ready' || discoveredStatus === 'partial')) {
                        setAnalysisStatus('completed');
                    }
                }
            } catch (error) {
                if (!cancelled) {
                    setFetchError(error instanceof Error ? error.message : 'Unable to load QC status.');
                }
            } finally {
                if (!cancelled) setInitialLoading(false);
            }
        };

        initialize();
        return () => { cancelled = true; };
    }, [workbench.id, isQCEnabled]);

    useEffect(() => {
        if (analysisStatus !== 'completing') return undefined;
        let cancelled = false;
        const loadCompletedResults = async () => {
            await fetchQCResults(5, () => cancelled);
            if (!cancelled) setAnalysisStatus('completed');
        };
        loadCompletedResults();
        return () => { cancelled = true; };
    }, [analysisStatus, workbench.id]);

    if (workbench.source_mode === 'existing_workbench' || workbench.source_mode === 'matrix_files') {
        return (
            <div className="border border-slate-200 bg-white p-6 shadow-sm rounded-lg">
                <h3 className="text-lg font-semibold text-slate-800">Quality Control</h3>
                <p className="mt-2 text-sm text-slate-600">Raw-read QC is not available for imported matrices.</p>
            </div>
        );
    }

    if (!isQCEnabled) {
        return (
            <div className="h-full flex items-center justify-center p-6">
                <div className="max-w-xl w-full border border-slate-200 bg-slate-50 p-6 rounded-lg">
                    <h3 className="text-lg font-semibold text-slate-800">Quality Control Disabled</h3>
                    <p className="mt-2 text-sm text-slate-600">The QC step was not selected for this workbench.</p>
                </div>
            </div>
        );
    }

    if (initialLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="w-10 h-10 border-4 border-cyan-600 border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    if (analysisStatus === 'not_started' || analysisStatus === 'pending') {
        return (
            <div className="border border-slate-200 bg-white p-6 rounded-lg">
                <h3 className="text-lg font-semibold text-slate-800">Quality Control Pending</h3>
                <p className="mt-2 text-sm text-slate-600">Waiting for the preceding pipeline step.</p>
            </div>
        );
    }

    if (analysisStatus === 'running' || analysisStatus === 'completing') {
        const completed = qcProgress?.completed_files || 0;
        const total = qcProgress?.total_files || 0;
        const percent = qcProgress?.progress_percent || 0;
        return (
            <div className="border border-slate-200 bg-white p-6 rounded-lg">
                <div className="flex items-center justify-between text-sm text-slate-700">
                    <h3 className="text-lg font-semibold text-slate-800">
                        {analysisStatus === 'completing' ? 'Preparing QC Results' : 'Quality Control Running'}
                    </h3>
                    <span>{completed} / {total}</span>
                </div>
                <div className="mt-4 h-3 overflow-hidden bg-slate-200 rounded-full">
                    <div className="h-full bg-cyan-600 transition-all" style={{ width: `${Math.min(percent, 100)}%` }} />
                </div>
            </div>
        );
    }

    const selectedSample = selectedSampleId
        ? samples.find(sample => sample.id === selectedSampleId) || null
        : null;
    const hasResults = samples.length > 0;
    const showWarning = resultStatus === 'partial' || analysisStatus === 'failed';

    if (!hasResults) {
        return (
            <div className="max-w-3xl border border-red-200 bg-red-50 p-6 rounded-lg">
                <h3 className="text-lg font-semibold text-red-900">QC Results Unavailable</h3>
                <p className="mt-2 text-sm text-red-800">
                    {fetchError || 'FastQC finished without any result that VizR can display.'}
                </p>
                {resultCounts.expected > 0 && (
                    <p className="mt-2 text-sm text-red-700">
                        Displayable reports: {resultCounts.parsed} / {resultCounts.expected}
                        {resultCounts.failed > 0 ? `; failed: ${resultCounts.failed}` : ''}
                    </p>
                )}
                {resultErrors.slice(0, 8).map((item, index) => (
                    <div key={`${item.report || 'qc'}-${index}`} className="mt-2 text-sm text-red-700">
                        <strong>{item.report || item.sample || 'QC'}:</strong> {item.errors.join('; ')}
                    </div>
                ))}
                <button
                    type="button"
                    onClick={retryResults}
                    disabled={retrying}
                    className="mt-5 px-4 py-2 bg-red-700 text-white rounded-md hover:bg-red-800 disabled:opacity-50"
                >
                    {retrying ? 'Retrying...' : 'Retry'}
                </button>
            </div>
        );
    }

    return (
        <div className="flex h-full min-h-0 flex-col">
            {showWarning && (
                <div className="border-b border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-900">
                    <div className="font-semibold">QC completed with unavailable reports</div>
                    <div className="mt-1">
                        Displayable reports: {resultCounts.parsed} / {resultCounts.expected || samples.length}.
                        {resultCounts.failed > 0 ? ` Failed: ${resultCounts.failed}.` : ''}
                        Downstream analysis continued with the configured input data.
                    </div>
                    {resultErrors.slice(0, 5).map((item, index) => (
                        <div key={`${item.report || 'qc'}-${index}`} className="mt-1">
                            <strong>{item.report || item.sample || 'QC'}:</strong> {item.errors.join('; ')}
                        </div>
                    ))}
                </div>
            )}
            {fetchError && (
                <div className="flex items-center justify-between border-b border-red-200 bg-red-50 px-5 py-3 text-sm text-red-800">
                    <span>{fetchError}</span>
                    <button type="button" onClick={retryResults} disabled={retrying} className="font-semibold underline">
                        {retrying ? 'Retrying...' : 'Retry'}
                    </button>
                </div>
            )}
            <div className="flex min-h-0 flex-1">
                <QCSidebar
                    samples={samples}
                    selectedSampleId={selectedSampleId}
                    onSelectSample={setSelectedSampleId}
                />
                <main className="flex-1 overflow-y-auto bg-white">
                    {selectedSample ? (
                        <QCSampleDetail sample={selectedSample} />
                    ) : (
                        <QCSampleOverview
                            samples={samples}
                            onSelectSample={sample => setSelectedSampleId(sample.id)}
                            moduleStatistics={moduleStats || undefined}
                        />
                    )}
                </main>
            </div>
        </div>
    );
};

export default WorkbenchDetailQC;
