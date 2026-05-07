import React, { useState, useEffect, useRef } from 'react';
import { PipelineJobStatus } from '../types';
import StatusBadge from './StatusBadge';
import EditPipelineModal from './EditPipelineModal';

// Icons
const PlayIcon = ({ className = "w-5 h-5" }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
);

const StopIcon = ({ className = "w-5 h-5" }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        <rect x="9" y="9" width="6" height="6" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} />
    </svg>
);

const CheckIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" className={className} viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
    </svg>
);

const XIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" className={className} viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
    </svg>
);

const TrashIcon = ({ className = "w-5 h-5" }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
);

const ShareIcon = ({ className = "w-5 h-5" }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
    </svg>
);

const UserIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
    </svg>
);


// Types
interface SharedUser {
    id: number;
    username: string;
    email: string;
}

interface User {
    id: number;
    username: string;
    email: string;
}


// Main Overview Component
interface WorkbenchDetailOverviewProps {
    workbench: any;
    pipelineConfig: any;
    pipelineStepsData: any[];
    onStartAnalysis: () => void;
    onDeleteWorkbench: () => void;
    showComingSoon: () => void;
    pipelineStatus: PipelineJobStatus | null;
    onStopAnalysis: () => void;
    onRefreshData: () => Promise<void>;
}

const WorkbenchDetailOverview: React.FC<WorkbenchDetailOverviewProps> = ({
    workbench,
    pipelineConfig,
    pipelineStepsData,
    onStartAnalysis,
    onDeleteWorkbench,
    showComingSoon,
    pipelineStatus,
    onStopAnalysis,
    onRefreshData
}) => {
    // Share modal state
    const [isShareModalOpen, setIsShareModalOpen] = useState(false);
    const [sharedUsers, setSharedUsers] = useState<SharedUser[]>([]);
    const [allUsers, setAllUsers] = useState<User[]>([]);
    const [searchQuery, setSearchQuery] = useState('');
    const [isLoadingSharedUsers, setIsLoadingSharedUsers] = useState(false);
    const [shareError, setShareError] = useState<string | null>(null);

    // Edit pipeline modal state
    const [isEditPipelineModalOpen, setIsEditPipelineModalOpen] = useState(false);

    // Method text state
    const [methodText, setMethodText] = useState<string | null>(null);
    const [methodLoading, setMethodLoading] = useState(false);
    const [methodCopied, setMethodCopied] = useState(false);
    const methodTextRef = useRef<HTMLDivElement>(null);

    // Null safety check
    if (!workbench) {
        return (
            <div className="text-center py-8">
                <p className="text-slate-500">Loading workbench information...</p>
            </div>
        );
    }

    // Check if user is shared user (read-only access)
    const isSharedUser = workbench.workbench?.permission === 'shared' || workbench.permission === 'shared';

    // Load shared users when modal opens
    useEffect(() => {
        if (isShareModalOpen) {
            if (!isSharedUser) {
                loadSharedUsers();
                loadAllUsers();
            }
        }
    }, [isShareModalOpen]);

    const loadSharedUsers = async () => {
        setIsLoadingSharedUsers(true);
        setShareError(null);
        try {
            const workbenchId = workbench.workbench?.id || workbench.id;
            const response = await fetch(`/api/workbenches/${workbenchId}/shared-users`, {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('Failed to load shared users');
            }

            const data = await response.json();
            setSharedUsers(data.shared_users || []);
        } catch (error) {
            console.error('[Share] Failed to load shared users:', error);
            setShareError('Failed to load shared users');
        } finally {
            setIsLoadingSharedUsers(false);
        }
    };

    const loadAllUsers = async () => {
        try {
            const workbenchId = workbench.workbench?.id || workbench.id;
            const response = await fetch(`/api/workbenches/${workbenchId}/available-users`, {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('Failed to load users');
            }

            const data = await response.json();
            setAllUsers(data.users || []);
        } catch (error) {
            console.error('[Share] Failed to load users:', error);
        }
    };

    const handleAddUser = async (userId: number) => {
        const workbenchId = workbench.workbench?.id || workbench.id;

        try {
            const response = await fetch(`/api/workbenches/${workbenchId}/share`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({
                    user_ids: [userId]
                })
            });

            if (!response.ok) {
                throw new Error('Failed to add user');
            }

            await loadSharedUsers();
            await loadAllUsers();
        } catch (error) {
            console.error('[Share] Failed to add user:', error);
            setShareError('Failed to add user');
        }
    };

    const handleRemoveUser = async (userId: number) => {
        const workbenchId = workbench.workbench?.id || workbench.id;

        try {
            const response = await fetch(`/api/workbenches/${workbenchId}/share/${userId}`, {
                method: 'DELETE',
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('Failed to remove user');
            }

            await loadSharedUsers();
            await loadAllUsers();
        } catch (error) {
            console.error('[Share] Failed to remove user:', error);
            setShareError('Failed to remove user');
        }
    };

    const handleLeaveWorkbench = async () => {
        const workbenchId = workbench.workbench?.id || workbench.id;

        try {
            // Step 1: Get current user ID from auth profile endpoint
            const authResponse = await fetch('/api/auth/profile', {
                credentials: 'include'
            });

            if (!authResponse.ok) {
                throw new Error('Failed to get current user');
            }

            const authData = await authResponse.json();
            const currentUserId = authData.user?.id;

            if (!currentUserId) {
                setShareError('Unable to determine current user');
                return;
            }

            // Step 2: Remove current user from shared list
            const response = await fetch(`/api/workbenches/${workbenchId}/share/${currentUserId}`, {
                method: 'DELETE',
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('Failed to leave workbench');
            }

            // Close modal and redirect to workbench list
            setIsShareModalOpen(false);
            window.location.href = '/workbenches';
        } catch (error) {
            console.error('[Share] Failed to leave workbench:', error);
            setShareError('Failed to leave workbench');
        }
    };

    const filteredUsers = allUsers.filter(user => {
        // Filter by search query (available-users API already excludes shared users)
        if (searchQuery.trim() === '') return true;
        const query = searchQuery.toLowerCase();
        return user.username.toLowerCase().includes(query) ||
               user.email.toLowerCase().includes(query);
    });

    // Auto-fetch method text when pipeline is completed
    useEffect(() => {
        if (pipelineStatus?.status === 'completed') {
            const wbId = workbench?.workbench?.id || workbench?.id;
            if (!wbId) return;
            setMethodLoading(true);
            fetch(`/api/workbenches/${wbId}/method-text`, { credentials: 'include' })
                .then(res => res.ok ? res.json() : null)
                .then(data => { if (data) setMethodText(data.method_text); })
                .catch(err => console.error('Failed to fetch method text:', err))
                .finally(() => setMethodLoading(false));
        }
    }, [pipelineStatus?.status, workbench?.workbench?.id, workbench?.id]);

    const handlePipelineUpdate = async () => {

        try {
            // Refresh workbench data without full page reload
            await onRefreshData();
        } catch (error) {
        }
    };

    const getStepDisplayName = (stepId: string): string => {
        const stepNames: Record<string, string> = {
            'download': 'Data Download/Copy',
            'qc': 'Quality Control',
            'clean': 'Preprocessing',
            'alignment': 'Alignment',
            'count': 'Read Counting',
            'deg': 'DEG Analysis',
            'gsea': 'GSEA',
            'step_1_download': 'Data Download/Copy',
            'step_2_qc': 'Quality Control',
            'step_3_alignment': 'Alignment',
            'step_4_count': 'Read Counting',
            'step_5_deg': 'DEG Analysis',
            'step_6_gsea': 'GSEA'
        };
        return stepNames[stepId] || stepId;
    };

    try {
        return (
            <div className="space-y-6">
                {/* SECTION 1: HEADER */}
                <div className="bg-white rounded-xl border border-slate-200 p-6">
                    <div className="flex items-start justify-between">
                        <div className="flex-1">
                            <h2 className="text-2xl font-bold text-slate-800 mb-2">
                                {workbench.workbench?.name || workbench.name || 'Unknown'}
                            </h2>
                            <div className="flex items-center gap-4 text-sm text-slate-600 mb-3">
                                <div className="flex items-center gap-2">
                                    <span className="font-medium">Species:</span>
                                    <span>{workbench.workbench?.species || workbench.species || 'Not specified'}</span>
                                </div>
                            </div>
                            <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
                                <div>
                                    <span className="font-medium">Created:</span>{' '}
                                    {(workbench.workbench?.created_at || workbench.created_at) ?
                                        new Date(workbench.workbench?.created_at || workbench.created_at).toLocaleString('ko-KR', {
                                            year: 'numeric',
                                            month: 'long',
                                            day: 'numeric',
                                            hour: '2-digit',
                                            minute: '2-digit',
                                            second: '2-digit',
                                            hour12: false
                                        }) : 'Unknown'}
                                </div>
                                <div>
                                    <span className="font-medium">Updated:</span>{' '}
                                    {(workbench.workbench?.updated_at || workbench.updated_at) ?
                                        new Date(workbench.workbench?.updated_at || workbench.updated_at).toLocaleString('ko-KR', {
                                            year: 'numeric',
                                            month: 'long',
                                            day: 'numeric',
                                            hour: '2-digit',
                                            minute: '2-digit',
                                            second: '2-digit',
                                            hour12: false
                                        }) : 'Unknown'}
                                </div>
                                <div>
                                    <span className="font-medium">Created by:</span>{' '}
                                    {workbench.workbench?.created_by || workbench.created_by || 'Unknown'}
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center gap-3">
                            <button
                                onClick={() => setIsShareModalOpen(true)}
                                className={`px-4 py-2 rounded-lg transition-colors flex items-center gap-2 text-sm font-medium ${
                                    isSharedUser
                                        ? 'bg-orange-50 border border-orange-200 text-orange-700 hover:bg-orange-100'
                                        : 'bg-blue-50 border border-blue-200 text-blue-700 hover:bg-blue-100'
                                }`}
                                title={isSharedUser ? 'Leave this shared workbench' : 'Share this workbench with others'}
                            >
                                <ShareIcon className="w-4 h-4" />
                                {isSharedUser ? 'Leave' : 'Share'}
                            </button>
                            <button
                                onClick={() => setIsEditPipelineModalOpen(true)}
                                disabled={isSharedUser || pipelineStatus?.status === 'running' || pipelineStatus?.status === 'pending'}
                                className={`px-4 py-2 rounded-lg transition-colors flex items-center gap-2 text-sm font-medium ${
                                    isSharedUser || pipelineStatus?.status === 'running' || pipelineStatus?.status === 'pending'
                                        ? 'bg-gray-100 border border-gray-300 text-gray-400 cursor-not-allowed'
                                        : 'bg-purple-50 border border-purple-200 text-purple-700 hover:bg-purple-100'
                                }`}
                                title={
                                    isSharedUser
                                        ? 'Only the owner can edit pipeline'
                                        : pipelineStatus?.status === 'running' || pipelineStatus?.status === 'pending'
                                            ? 'Cannot edit pipeline while it is running'
                                            : 'Edit pipeline configuration'
                                }
                            >
                                Edit Pipeline
                            </button>
                            <button
                                onClick={onDeleteWorkbench}
                                disabled={isSharedUser}
                                className={`px-4 py-2 rounded-lg transition-colors flex items-center gap-2 text-sm font-medium ${
                                    isSharedUser
                                        ? 'bg-gray-100 border border-gray-300 text-gray-400 cursor-not-allowed'
                                        : 'bg-red-50 border border-red-200 text-red-700 hover:bg-red-100'
                                }`}
                                title={isSharedUser ? 'Only the owner can delete this workbench' : ''}
                            >
                                <TrashIcon className="w-4 h-4" />
                                Delete
                            </button>
                        </div>
                    </div>
                    {isSharedUser && (
                        <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                            <p className="text-sm text-blue-700">
                                📖 <span className="font-medium">Read-Only Access:</span> This workbench is shared with you. You can view all analysis results, but cannot start, stop, or delete the workbench.
                            </p>
                        </div>
                    )}
                </div>

                {/* SECTION 2: PIPELINE STATUS */}
                <div className={`rounded-xl p-6 border ${
                    !pipelineStatus ? 'bg-white border-slate-200' :
                    pipelineStatus.status === 'running' ? 'bg-gradient-to-r from-blue-50 to-blue-100 border-blue-200' :
                    pipelineStatus.status === 'completed' ? 'bg-gradient-to-r from-green-50 to-green-100 border-green-200' :
                    pipelineStatus.status === 'failed' ? 'bg-gradient-to-r from-red-50 to-red-100 border-red-200' :
                    'bg-gradient-to-r from-gray-50 to-gray-100 border-gray-200'
                }`}>
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                            {!pipelineStatus ? (
                                <>
                                    <div className="w-3 h-3 bg-slate-400 rounded-full" />
                                    <h3 className="text-lg font-semibold text-slate-700">Not Started</h3>
                                </>
                            ) : pipelineStatus.status === 'running' ? (
                                <>
                                    <div className="w-3 h-3 bg-blue-500 rounded-full animate-pulse" />
                                    <h3 className="text-lg font-semibold text-blue-800">Pipeline Running</h3>
                                </>
                            ) : pipelineStatus.status === 'completed' ? (
                                <>
                                    <CheckIcon className="w-5 h-5 text-green-600" />
                                    <h3 className="text-lg font-semibold text-green-800">Pipeline Completed</h3>
                                </>
                            ) : pipelineStatus.status === 'failed' ? (
                                <>
                                    <XIcon className="w-5 h-5 text-red-600" />
                                    <h3 className="text-lg font-semibold text-red-800">Pipeline Failed</h3>
                                </>
                            ) : pipelineStatus.status === 'pending' ? (
                                <>
                                    <div className="w-3 h-3 bg-yellow-500 rounded-full animate-pulse" />
                                    <h3 className="text-lg font-semibold text-yellow-800">Pipeline Starting</h3>
                                </>
                            ) : null}
                        </div>
                        {pipelineStatus && (
                            <div className="text-sm font-medium text-slate-600">
                                {pipelineStatus.completed_steps}/{pipelineStatus.total_steps} steps
                            </div>
                        )}
                    </div>

                    {/* Progress Bar */}
                    {pipelineStatus && (
                        <div className="mb-4">
                            <div className="w-full bg-gray-200 rounded-full h-3">
                                <div
                                    className={`h-3 rounded-full transition-all duration-500 ${
                                        pipelineStatus.status === 'running' ? 'bg-blue-600' :
                                        pipelineStatus.status === 'completed' ? 'bg-green-600' :
                                        pipelineStatus.status === 'failed' ? 'bg-red-600' :
                                        'bg-gray-400'
                                    }`}
                                    style={{ width: `${pipelineStatus.progress_percentage || 0}%` }}
                                />
                            </div>
                        </div>
                    )}

                    {/* Current Step */}
                    {pipelineStatus && pipelineStatus.status === 'running' && pipelineStatus.current_step && (
                        <div className="text-sm text-slate-700 mb-3">
                            <span className="font-medium">Current Step:</span>{' '}
                            {getStepDisplayName(pipelineStatus.current_step)}
                        </div>
                    )}

                    {/* Time Information */}
                    {pipelineStatus && pipelineStatus.started_at && (
                        <div className="text-xs text-slate-600 mb-4">
                            <span className="font-medium">Started:</span>{' '}
                            {new Date(pipelineStatus.started_at).toLocaleString()}
                            {pipelineStatus.completed_at && pipelineStatus.status !== 'running' && pipelineStatus.status !== 'pending' && (
                                <>
                                    <span className="mx-2">|</span>
                                    <span className="font-medium">Completed:</span>{' '}
                                    {new Date(pipelineStatus.completed_at).toLocaleString()}
                                </>
                            )}
                        </div>
                    )}

                    {/* Error Message */}
                    {pipelineStatus && pipelineStatus.status === 'failed' && pipelineStatus.error_message && (
                        <div className="bg-red-100 border border-red-300 rounded-lg p-3 mb-4">
                            <p className="text-sm text-red-800">
                                <span className="font-medium">Error:</span> {pipelineStatus.error_message}
                            </p>
                        </div>
                    )}

                    {/* Action Buttons */}
                    <div className="flex gap-3">
                        <button
                            onClick={onStartAnalysis}
                            disabled={isSharedUser || pipelineStatus?.status === 'running' || pipelineStatus?.status === 'pending'}
                            className={`px-6 py-2.5 font-semibold rounded-lg transition-colors flex items-center gap-2 text-sm ${
                                isSharedUser || pipelineStatus?.status === 'running' || pipelineStatus?.status === 'pending'
                                    ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                    : 'bg-green-600 text-white hover:bg-green-700'
                            }`}
                            title={isSharedUser ? 'Only the owner can start analysis' : ''}
                        >
                            <PlayIcon className="w-4 h-4" />
                            Start Analysis
                        </button>
                        <button
                            onClick={onStopAnalysis}
                            disabled={isSharedUser || !pipelineStatus || (pipelineStatus.status !== 'running' && pipelineStatus.status !== 'pending')}
                            className={`px-6 py-2.5 font-semibold rounded-lg transition-colors flex items-center gap-2 text-sm ${
                                isSharedUser
                                    ? 'bg-gray-100 border border-gray-300 text-gray-400 cursor-not-allowed'
                                    : pipelineStatus?.status === 'running' || pipelineStatus?.status === 'pending'
                                        ? 'bg-red-500 text-white hover:bg-red-600'
                                        : 'bg-gray-100 border border-gray-300 text-gray-400 cursor-not-allowed'
                            }`}
                            title={isSharedUser ? 'Only the owner can stop analysis' : ''}
                        >
                            <StopIcon className="w-4 h-4" />
                            Stop Analysis
                        </button>
                    </div>
                </div>

                {/* SECTION 3: DATA & PIPELINE INFO */}
                <div className="bg-white rounded-xl border border-slate-200 p-6">
                    {/* Data Summary */}
                    <div className="mb-6">
                        <h3 className="text-lg font-semibold text-slate-800 mb-4">Data Overview</h3>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-4 border border-blue-200">
                                <div className="text-sm font-medium text-blue-700 mb-1">Data Layout</div>
                                <div className="text-lg font-bold text-blue-900">
                                    {pipelineConfig?.data_layout === 'se' ? 'Single-End (SE)' :
                                     pipelineConfig?.data_layout === 'pe' ? 'Paired-End (PE)' : 'Not configured'}
                                </div>
                            </div>
                            <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-lg p-4 border border-purple-200">
                                <div className="text-sm font-medium text-purple-700 mb-1">Samples</div>
                                <div className="text-lg font-bold text-purple-900">
                                    {workbench.samples_count || 0}
                                </div>
                            </div>
                            <div className="bg-gradient-to-br from-amber-50 to-amber-100 rounded-lg p-4 border border-amber-200">
                                <div className="text-sm font-medium text-amber-700 mb-1">Files</div>
                                <div className="text-lg font-bold text-amber-900">
                                    {workbench.raw_files_count || 0}
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Pipeline Steps */}
                    <div>
                        <h3 className="text-lg font-semibold text-slate-800 mb-4">Pipeline Steps</h3>
                        <div className="flex flex-wrap items-center gap-2 overflow-x-auto">
                            {pipelineStepsData && pipelineStepsData.length > 0 ? (
                                pipelineStepsData.map((step: any, index: number) => (
                                    <div key={`${step.step}_${step.tool}_${index}`} className="flex items-center gap-2 bg-slate-50 rounded-lg px-4 py-3 border border-slate-200">
                                        <div className="w-7 h-7 bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-bold">
                                            {index + 1}
                                        </div>
                                        <div>
                                            <div className="text-sm font-semibold text-slate-800">
                                                {step.description || step.step}
                                            </div>
                                            <div className="text-xs text-slate-500">
                                                {step.tool === 'trimmomatic_prinseq' ? 'Trimmomatic → PRINSEQ' : step.tool}
                                            </div>
                                        </div>
                                    </div>
                                ))
                            ) : (
                                ['Quality Control', 'Sequence Cleaning', 'Read Alignment', 'Read Counting', 'Differential Expression'].map((step, index) => (
                                    <div key={step} className="flex items-center gap-2 bg-slate-50 rounded-lg px-4 py-3 border border-slate-200">
                                        <div className="w-7 h-7 bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-bold">
                                            {index + 1}
                                        </div>
                                        <div>
                                            <div className="text-sm font-semibold text-slate-800">{step}</div>
                                            <div className="text-xs text-slate-500">
                                                {index === 0 && 'FastQC'}
                                                {index === 1 && 'PRINSEQ'}
                                                {index === 2 && 'HISAT2'}
                                                {index === 3 && 'StringTie'}
                                                {index === 4 && 'DESeq2'}
                                            </div>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>

                {/* SECTION 4: METHOD TEXT FOR PAPER */}
                {pipelineStatus?.status === 'completed' && (
                    <div className="bg-white rounded-xl border border-slate-200 p-6">
                        <div className="mb-4">
                            <h3 className="text-lg font-semibold text-slate-800">Method</h3>
                            <p className="text-sm text-slate-500 mt-1">
                                Auto-generated text based on the pipeline configuration. Copy and use in your manuscript.
                            </p>
                        </div>

                        {methodLoading && (
                            <div className="flex items-center justify-center py-8">
                                <div className="animate-spin w-6 h-6 border-3 border-primary border-t-transparent rounded-full"></div>
                                <span className="ml-3 text-slate-500 text-sm">Generating method text...</span>
                            </div>
                        )}

                        {methodText && (
                            <div>
                                <div
                                    ref={methodTextRef}
                                    className="bg-slate-50 rounded-lg p-5 text-slate-700 leading-relaxed text-sm border border-slate-200 select-all cursor-text"
                                >
                                    {methodText}
                                </div>
                                <div className="flex items-center justify-between mt-3">
                                    <p className="text-xs text-slate-500">
                                        <span className="font-medium">Reference:</span> Jeon et al. (2026). VizR: A Web-Based Integrated Platform for End-to-End RNA-Seq Analysis with Interactive Visualization in Plant Biology.
                                    </p>
                                    <button
                                        onClick={async () => {
                                            try {
                                                await navigator.clipboard.writeText(methodText);
                                                setMethodCopied(true);
                                                setTimeout(() => setMethodCopied(false), 2000);
                                            } catch {
                                                if (methodTextRef.current) {
                                                    const range = document.createRange();
                                                    range.selectNodeContents(methodTextRef.current);
                                                    const sel = window.getSelection();
                                                    sel?.removeAllRanges();
                                                    sel?.addRange(range);
                                                    document.execCommand('copy');
                                                    sel?.removeAllRanges();
                                                    setMethodCopied(true);
                                                    setTimeout(() => setMethodCopied(false), 2000);
                                                }
                                            }
                                        }}
                                        className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                                            methodCopied
                                                ? 'bg-green-100 text-green-700 border border-green-300'
                                                : 'bg-primary text-white hover:bg-primary-dark'
                                        }`}
                                    >
                                        {methodCopied ? (
                                            <>
                                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                                </svg>
                                                Copied!
                                            </>
                                        ) : (
                                            <>
                                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                                                </svg>
                                                Copy to Clipboard
                                            </>
                                        )}
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* SHARE MODAL */}
                {isShareModalOpen && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                        <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[90vh] flex flex-col">
                            {/* Modal Header */}
                            <div className="flex items-center justify-between p-6 border-b border-slate-200">
                                <h3 className="text-xl font-bold text-slate-800">
                                    {isSharedUser ? 'Leave Shared Workbench' : 'Share Workbench'}
                                </h3>
                                <button
                                    onClick={() => {
                                        setIsShareModalOpen(false);
                                        setSearchQuery('');
                                        setShareError(null);
                                    }}
                                    className="text-slate-400 hover:text-slate-600 transition-colors"
                                >
                                    <XIcon className="w-6 h-6" />
                                </button>
                            </div>

                            {/* Modal Body */}
                            <div className="flex-1 overflow-y-auto p-6 space-y-6">
                                {/* Error Message */}
                                {shareError && (
                                    <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                                        <p className="text-sm text-red-700">{shareError}</p>
                                    </div>
                                )}

                                {/* Shared User View - Leave Workbench */}
                                {isSharedUser ? (
                                    <div className="space-y-4">
                                        <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
                                            <p className="text-sm text-orange-800 mb-3">
                                                This workbench has been shared with you. If you no longer need access, you can leave this shared workbench.
                                            </p>
                                            <p className="text-xs text-orange-700">
                                                ⚠️ <strong>Note:</strong> After leaving, you won't be able to access this workbench unless the owner shares it with you again.
                                            </p>
                                        </div>

                                        <div className="flex justify-center">
                                            <button
                                                onClick={handleLeaveWorkbench}
                                                className="px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-sm font-medium flex items-center gap-2"
                                            >
                                                <XIcon className="w-4 h-4" />
                                                Leave this Workbench
                                            </button>
                                        </div>
                                    </div>
                                ) : (
                                    <>
                                        {/* Owner View - Normal Share Interface */}

                                {/* Currently Shared Users */}
                                <div>
                                    <h4 className="text-sm font-semibold text-slate-700 mb-3">
                                        Shared with ({sharedUsers.length})
                                    </h4>
                                    {isLoadingSharedUsers ? (
                                        <div className="text-center py-4">
                                            <p className="text-sm text-slate-500">Loading...</p>
                                        </div>
                                    ) : sharedUsers.length === 0 ? (
                                        <div className="text-center py-4 bg-slate-50 rounded-lg border border-slate-200">
                                            <p className="text-sm text-slate-500">
                                                Not shared with anyone yet
                                            </p>
                                        </div>
                                    ) : (
                                        <div className="space-y-2">
                                            {sharedUsers.map((user) => (
                                                <div
                                                    key={user.id}
                                                    className="flex items-center justify-between p-3 bg-blue-50 border border-blue-200 rounded-lg"
                                                >
                                                    <div className="flex items-center gap-3">
                                                        <div className="w-8 h-8 bg-blue-200 rounded-full flex items-center justify-center">
                                                            <UserIcon className="w-4 h-4 text-blue-700" />
                                                        </div>
                                                        <div>
                                                            <p className="text-sm font-medium text-slate-800">
                                                                {user.username}
                                                            </p>
                                                            <p className="text-xs text-slate-500">
                                                                {user.email}
                                                            </p>
                                                        </div>
                                                    </div>
                                                    <button
                                                        onClick={() => handleRemoveUser(user.id)}
                                                        className="px-3 py-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded hover:bg-red-100 transition-colors"
                                                    >
                                                        Remove
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {/* Add Users */}
                                <div>
                                    <h4 className="text-sm font-semibold text-slate-700 mb-3">
                                        Add Users
                                    </h4>

                                    {/* Search Input */}
                                    <div className="mb-3">
                                        <input
                                            type="text"
                                            placeholder="Search by username or email..."
                                            value={searchQuery}
                                            onChange={(e) => setSearchQuery(e.target.value)}
                                            className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                        />
                                    </div>

                                    {/* Available Users List */}
                                    <div className="space-y-2 max-h-64 overflow-y-auto">
                                        {filteredUsers.length === 0 ? (
                                            <div className="text-center py-4 bg-slate-50 rounded-lg border border-slate-200">
                                                <p className="text-sm text-slate-500">
                                                    {searchQuery.trim() === ''
                                                        ? 'No available users to share with'
                                                        : 'No users found matching your search'}
                                                </p>
                                            </div>
                                        ) : (
                                            filteredUsers.map((user) => (
                                                <div
                                                    key={user.id}
                                                    className="flex items-center justify-between p-3 bg-slate-50 border border-slate-200 rounded-lg hover:bg-slate-100 transition-colors"
                                                >
                                                    <div className="flex items-center gap-3">
                                                        <div className="w-8 h-8 bg-slate-200 rounded-full flex items-center justify-center">
                                                            <UserIcon className="w-4 h-4 text-slate-600" />
                                                        </div>
                                                        <div>
                                                            <p className="text-sm font-medium text-slate-800">
                                                                {user.username}
                                                            </p>
                                                            <p className="text-xs text-slate-500">
                                                                {user.email}
                                                            </p>
                                                        </div>
                                                    </div>
                                                    <button
                                                        onClick={() => handleAddUser(user.id)}
                                                        className="px-3 py-1 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded hover:bg-blue-100 transition-colors"
                                                    >
                                                        Add
                                                    </button>
                                                </div>
                                            ))
                                        )}
                                    </div>
                                </div>
                                    </>
                                )}
                            </div>

                            {/* Modal Footer */}
                            <div className="flex justify-end p-6 border-t border-slate-200">
                                <button
                                    onClick={() => {
                                        setIsShareModalOpen(false);
                                        setSearchQuery('');
                                        setShareError(null);
                                    }}
                                    className="px-6 py-2 bg-slate-600 text-white rounded-lg hover:bg-slate-700 transition-colors text-sm font-medium"
                                >
                                    Close
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* EDIT PIPELINE MODAL */}
                {isEditPipelineModalOpen && (
                    <EditPipelineModal
                        isOpen={isEditPipelineModalOpen}
                        onClose={() => setIsEditPipelineModalOpen(false)}
                        workbenchId={workbench.workbench?.id || workbench.id}
                        currentPipelineSteps={pipelineStepsData}
                        species={workbench.workbench?.species || workbench.species}
                        sourceMode={workbench.workbench?.source_mode || workbench.source_mode}
                        currentReferenceSet={
                            pipelineStepsData.find((s: any) => s.step === 'alignment')?.parameters?.reference_set || 'TAIR10'
                        }
                        onUpdate={handlePipelineUpdate}
                    />
                )}
            </div>
        );
    } catch (error) {
        return (
            <div className="text-center py-12">
                <div className="text-red-500 mb-2">⚠️ Error Occurred</div>
                <p className="text-slate-600 mb-4">An error occurred during component rendering.</p>
                <pre className="text-xs text-slate-500 bg-slate-100 p-2 rounded">
                    {error?.toString()}
                </pre>
            </div>
        );
    }
};

export default WorkbenchDetailOverview;
