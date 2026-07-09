import React, { useEffect, useState } from 'react';
import useWebSocket from '../src/hooks/useWebSocket';
import { Workbench, StepDetail } from '../types';

interface FileState {
    id: string;
    fileName: string;
    index: number;
    hasReceivedData: boolean;
    progress: number;
    status: 'pending' | 'downloading' | 'completed' | 'compressed' | 'failed';
    size: number;
    downloaded: number;
}

interface FileMapping {
    id?: number;
    sample_id?: number;
    file_type?: 'file1' | 'file2';
    file1: string;
    file2?: string;
    groupName: string;
    sampleName: string;
}

interface WorkbenchDetailRawDataProps {
    workbench: Workbench;
    fileMappings: FileMapping[];
    pipelineStepsData: StepDetail[];
}

const formatSize = (bytes: number): string => {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const base = 1024;
    const unitIndex = Math.floor(Math.log(bytes) / Math.log(base));
    return `${parseFloat((bytes / Math.pow(base, unitIndex)).toFixed(2))} ${units[unitIndex]}`;
};

const FileProgressItem = ({ file }: { file: FileState }) => {
    const { hasReceivedData, progress, status, fileName, index, size, downloaded } = file;

    const statusColor =
        status === 'completed'
            ? 'bg-green-500'
            : status === 'compressed'
              ? 'bg-purple-500'
              : status === 'downloading'
                ? 'bg-blue-500'
                : status === 'failed'
                  ? 'bg-red-500'
                  : 'bg-slate-400';

    return (
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md">
            <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-600">
                        {index}
                    </div>
                    <div>
                        <div className="font-medium text-slate-800">{fileName}</div>
                        <div className="flex items-center space-x-2 text-xs capitalize text-slate-500">
                            <span>Status: {status}</span>
                            <div className={`h-2 w-2 rounded-full ${statusColor} ${status === 'downloading' ? 'animate-pulse' : ''}`} />
                        </div>
                    </div>
                </div>
                <div className="text-right">
                    {hasReceivedData ? (
                        <>
                            <div className="text-sm font-medium text-slate-700">{progress.toFixed(1)}%</div>
                            <div className="text-xs text-slate-500">
                                {formatSize(downloaded)} / {formatSize(size)}
                            </div>
                        </>
                    ) : (
                        <div className="text-xs text-slate-400">- / {formatSize(size)}</div>
                    )}
                </div>
            </div>

            {hasReceivedData ? (
                <div className="h-2 w-full rounded-full bg-slate-200">
                    <div
                        className={`h-2 rounded-full transition-all duration-300 ${statusColor}`}
                        style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
                    />
                </div>
            ) : (
                <div className="flex items-center justify-center space-x-2 text-slate-500">
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-blue-500" />
                    <span className="text-sm">Waiting for download to start...</span>
                </div>
            )}
        </div>
    );
};

const WorkbenchDetailRawData: React.FC<WorkbenchDetailRawDataProps> = ({
    workbench,
    fileMappings,
    pipelineStepsData,
}) => {
    const [progressData, setProgressData] = useState<Record<string, any>>({});
    const [fileStates, setFileStates] = useState<Record<string, FileState>>({});

    if (!workbench || !workbench.id) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                <span className="ml-3 text-slate-600">Loading workbench data...</span>
            </div>
        );
    }

    const getDataInputMethod = () => {
        if (!pipelineStepsData || pipelineStepsData.length === 0) return null;
        const downloadStep = pipelineStepsData.find((step) => step.step === 'download');
        return downloadStep?.parameters?.dataInputMethod || null;
    };

    const dataInputMethod = getDataInputMethod();

    useWebSocket({
        workbenchId: workbench.id,
        taskType: 'data_download',
        enabled: true,
        onProgressUpdate: (data) => {
            const progressInfo = data.data || data;
            const progressKey = progressInfo.srr_run || progressInfo.filename;
            if (!progressKey) return;

            setProgressData((prev) => ({
                ...prev,
                [progressKey]: progressInfo,
            }));
        },
    });

    useEffect(() => {
        const fetchDownloadProgress = async () => {
            try {
                const response = await fetch(`/api/workbenches/${workbench.id}/download-progress`, {
                    credentials: 'include',
                });
                if (!response.ok) return;

                const data = await response.json();
                if (!data.files || Object.keys(data.files).length === 0) return;

                const initialFileStates: Record<string, FileState> = {};
                let fileIndex = 1;

                Object.entries(data.files).forEach(([fileName, fileData]: [string, any]) => {
                    initialFileStates[fileName] = {
                        id: `file-${fileIndex}`,
                        fileName,
                        index: fileIndex,
                        hasReceivedData: (fileData.progress || 0) > 0,
                        progress: fileData.progress || 0,
                        status: fileData.status || 'pending',
                        size: fileData.file_size || fileData.total_bytes || 0,
                        downloaded: fileData.downloaded_size || fileData.copied_bytes || 0,
                    };
                    fileIndex += 1;
                });

                setFileStates(initialFileStates);
            } catch {
                // Keep the page stable even if the bootstrap request fails.
            }
        };

        fetchDownloadProgress();
    }, [workbench.id]);

    useEffect(() => {
        if (Object.keys(progressData).length === 0) return;

        setFileStates((prevStates) => {
            const updatedStates = { ...prevStates };

            Object.entries(progressData).forEach(([fileName, data]: [string, any]) => {
                const progress = data.progress_percent || data.progress || 0;
                const size = data.total_bytes || data.file_size || updatedStates[fileName]?.size || 0;
                let downloaded = data.copied_bytes || data.downloaded_size || 0;

                if (downloaded === 0 && progress > 0 && size > 0) {
                    downloaded = Math.round((size * progress) / 100);
                }

                if (updatedStates[fileName]) {
                    updatedStates[fileName] = {
                        ...updatedStates[fileName],
                        hasReceivedData: true,
                        progress,
                        status: data.status || 'downloading',
                        downloaded,
                        size,
                    };
                    return;
                }

                const newIndex = Object.keys(updatedStates).length + 1;
                updatedStates[fileName] = {
                    id: `file-${newIndex}`,
                    fileName,
                    index: newIndex,
                    hasReceivedData: true,
                    progress,
                    status: data.status || 'downloading',
                    size,
                    downloaded,
                };
            });

            return updatedStates;
        });
    }, [progressData]);

    const fileList = Object.values(fileStates).sort((a, b) => a.index - b.index);
    const downloadingCount = fileList.filter((file) => file.status === 'downloading').length;
    const completedCount = fileList.filter((file) => file.status === 'completed').length;
    const totalSize = fileList.reduce((sum, file) => sum + (file.size || 0), 0);

    if (workbench.source_mode === 'existing_workbench' || workbench.source_mode === 'matrix_files') {
        return (
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="text-lg font-semibold text-slate-800">Raw Data</h3>
                <p className="mt-2 text-sm text-slate-600">
                    This workbench was created from imported matrices. Raw data files are not part of this workflow.
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="rounded-xl border border-purple-200 bg-gradient-to-br from-purple-50 via-blue-50 to-indigo-50 p-6">
                <div className="mb-2 flex items-center space-x-2">
                    <h3 className="text-lg font-semibold text-slate-800">Raw Data</h3>
                </div>
                <p className="mb-6 text-sm text-slate-600">
                    This page summarizes the raw data files associated with the current workbench and their current file status.
                </p>

                {fileList.length > 0 ? (
                    <>
                        <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-4">
                            <div className="rounded-lg border border-white/50 bg-white/80 p-4 backdrop-blur">
                                <p className="text-sm text-slate-600">Total Files</p>
                                <p className="text-xl font-bold text-slate-800">{fileList.length}</p>
                            </div>
                            <div className="rounded-lg border border-white/50 bg-white/80 p-4 backdrop-blur">
                                <p className="text-sm text-slate-600">Downloading</p>
                                <p className="text-xl font-bold text-blue-600">{downloadingCount}</p>
                            </div>
                            <div className="rounded-lg border border-white/50 bg-white/80 p-4 backdrop-blur">
                                <p className="text-sm text-slate-600">Completed</p>
                                <p className="text-xl font-bold text-green-600">{completedCount}</p>
                            </div>
                            <div className="rounded-lg border border-white/50 bg-white/80 p-4 backdrop-blur">
                                <p className="text-sm text-slate-600">Total Size</p>
                                <p className="text-xl font-bold text-slate-800">{formatSize(totalSize)}</p>
                            </div>
                        </div>

                        <div className="space-y-3">
                            {fileList.map((file) => (
                                <FileProgressItem key={file.id} file={file} />
                            ))}
                        </div>
                    </>
                ) : (
                    <div className="py-8 text-center text-slate-500">
                        <div className="mb-3 text-4xl">...</div>
                        <p>Loading file information...</p>
                    </div>
                )}
            </div>

            <div className="rounded-xl border border-emerald-200 bg-gradient-to-r from-emerald-50 to-teal-50 p-6">
                <div className="mb-4 flex items-center space-x-2">
                    <h3 className="text-lg font-semibold text-slate-800">Data Source Information</h3>
                </div>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                    <div className="rounded-lg border border-white/50 bg-white/80 p-4 backdrop-blur">
                        <span className="text-sm font-medium text-slate-600">Input Method</span>
                        <p className="mt-1 font-semibold capitalize text-slate-800">
                            {dataInputMethod?.replace('_', ' ') || 'Not specified'}
                        </p>
                    </div>
                    {dataInputMethod === 'ncbi' && workbench.bioproject_id && (
                        <div className="rounded-lg border border-white/50 bg-white/80 p-4 backdrop-blur">
                            <span className="text-sm font-medium text-slate-600">NCBI BioProject</span>
                            <p className="mt-1 font-semibold text-slate-800">{workbench.bioproject_id}</p>
                        </div>
                    )}
                    {dataInputMethod === 'server' && workbench.server_file_paths && (
                        <div className="rounded-lg border border-white/50 bg-white/80 p-4 backdrop-blur">
                            <span className="text-sm font-medium text-slate-600">Server Paths</span>
                            <p className="mt-1 font-mono text-xs text-slate-800">
                                {workbench.server_file_paths.split('\n').length} path(s) configured
                            </p>
                        </div>
                    )}
                    <div className="rounded-lg border border-white/50 bg-white/80 p-4 backdrop-blur">
                        <span className="text-sm font-medium text-slate-600">Layout Type</span>
                        <p className="mt-1 font-semibold text-slate-800">
                            {workbench.layout === 'pe' ? 'Paired-End' : 'Single-End'}
                        </p>
                    </div>
                </div>
            </div>

            {fileMappings.length > 0 && (
                <div className="rounded-xl border border-rose-200 bg-gradient-to-r from-rose-50 to-pink-50 p-6">
                    <div className="mb-4 flex items-center space-x-2">
                        <h3 className="text-lg font-semibold text-slate-800">Sample Mapping Information</h3>
                    </div>

                    <div className="rounded-lg border border-white/50 bg-white/80 backdrop-blur">
                        <div className="overflow-x-auto">
                            <table className="min-w-full">
                                <thead className="bg-gradient-to-r from-slate-50 to-slate-100">
                                    <tr>
                                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-700">Group</th>
                                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-700">Sample</th>
                                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-700">Forward Read</th>
                                        {workbench.layout === 'pe' && (
                                            <th className="px-4 py-3 text-left text-sm font-medium text-slate-700">Reverse Read</th>
                                        )}
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-200">
                                    {fileMappings.map((mapping, index) => (
                                        <tr key={index} className="transition-colors hover:bg-slate-50">
                                            <td className="px-4 py-3 text-sm font-medium text-slate-800">{mapping.groupName}</td>
                                            <td className="px-4 py-3 text-sm text-slate-800">{mapping.sampleName}</td>
                                            <td className="px-4 py-3 text-sm text-slate-600">
                                                <span className="rounded bg-slate-100 px-2 py-1 font-mono text-xs">{mapping.file1}</span>
                                            </td>
                                            {workbench.layout === 'pe' && (
                                                <td className="px-4 py-3 text-sm text-slate-600">
                                                    <span className="rounded bg-slate-100 px-2 py-1 font-mono text-xs">{mapping.file2 || '-'}</span>
                                                </td>
                                            )}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default WorkbenchDetailRawData;
