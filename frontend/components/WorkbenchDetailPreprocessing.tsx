import React, { useState, useEffect } from 'react';
import { Workbench, StepDetail } from '../types';
import WorkbenchDetailPreprocessingTrimmomatic from './WorkbenchDetailPreprocessingTrimmomatic';
import WorkbenchDetailPreprocessingPrinseq from './WorkbenchDetailPreprocessingPrinseq';

// ========================================
// Type Definitions
// ========================================

type PreprocessingTab = 'trimmomatic' | 'prinseq';

interface WorkbenchDetailPreprocessingProps {
    workbench: Workbench;
    pipelineStepsData: StepDetail[];
    pipelineStatus?: any; // 실제 파이프라인 실행 상태
}

interface TabButtonProps {
    label: string;
    isActive: boolean;
    onClick: () => void;
    pipelineStatus?: 'pending' | 'running' | 'completed' | 'failed';
    showProgress?: boolean;
}

// ========================================
// Component Definitions
// ========================================

const TabButton = ({ label, isActive, onClick, pipelineStatus, showProgress }: TabButtonProps) => {
    const getStatusIndicator = () => {
        if (!showProgress || !pipelineStatus) {
            return null;
        }

        switch (pipelineStatus) {
            case 'pending':
                return <div className="w-2 h-2 bg-gray-400 rounded-full ml-2" />;
            case 'running':
                return (
                    <div className="relative ml-2">
                        <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                        <div className="absolute top-0 left-0 w-2 h-2 bg-green-400 rounded-full animate-ping opacity-75" />
                    </div>
                );
            case 'completed':
                return <div className="w-2 h-2 bg-green-600 rounded-full ml-2" />;
            case 'failed':
                return <div className="w-2 h-2 bg-red-600 rounded-full ml-2" />;
            default:
                return null;
        }
    };

    return (
        <button
            onClick={onClick}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors flex items-center ${
                isActive
                    ? 'text-blue-600 border-blue-500 bg-blue-50'
                    : 'text-slate-500 border-transparent hover:text-slate-700 hover:border-slate-300'
            }`}
        >
            {label}
            {getStatusIndicator()}
        </button>
    );
};



// ========================================
// Main Component
// ========================================

const WorkbenchDetailPreprocessing: React.FC<WorkbenchDetailPreprocessingProps> = ({ workbench, pipelineStepsData, pipelineStatus }) => {
    if (workbench.source_mode === 'existing_workbench' || workbench.source_mode === 'matrix_files') {
        return (
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="text-lg font-semibold text-slate-800">Preprocessing</h3>
                <p className="mt-2 text-sm text-slate-600">
                    This workbench starts from imported matrices, so trimming and preprocessing steps are not applicable.
                </p>
            </div>
        );
    }

    // Get pipeline status for each tab from actual pipeline execution status
    const getTabStatus = (toolName: string): 'pending' | 'running' | 'completed' | 'failed' => {
        // 파이프라인이 실행중이 아니면 pending
        if (!pipelineStatus) {
            return 'pending';
        }

        if (pipelineStatus.status !== 'running') {
            return 'pending';
        }

        // steps 배열에서 해당 툴의 상태 확인 (우선순위 높음)
        if (pipelineStatus.steps) {
            const toolStep = pipelineStatus.steps.find((s: any) => {
                return s.step_name === 'clean' && s.tool_name === toolName;
            });

            if (toolStep) {
                switch (toolStep.status) {
                    case 'completed':
                        return 'completed';
                    case 'running':
                        return 'running';
                    case 'failed':
                        return 'failed';
                    default:
                        return 'pending';
                }
            }
        }

        // steps 배열에서 찾지 못한 경우, current_step 확인
        if (pipelineStatus.current_step) {
            if (typeof pipelineStatus.current_step === 'string') {
                // current_step이 'clean'이고 steps에서 특정 도구를 찾지 못한 경우
                // 아직 해당 도구가 시작되지 않았다고 가정 (pending)
                if (pipelineStatus.current_step === 'clean') {
                    return 'pending';
                }
            } else if (typeof pipelineStatus.current_step === 'object') {
                // current_step이 객체인 경우 해당 툴인지 확인
                if (pipelineStatus.current_step.step_name === 'clean' && pipelineStatus.current_step.tool_name === toolName) {
                    return 'running';
                }
            }
        }

        return 'pending';
    };

    // Determine initial tab based on current running tool
    const getInitialTab = (): PreprocessingTab => {
        // Check if any tool is currently running
        const trimmomaticStatus = getTabStatus('trimmomatic');
        const prinseqStatus = getTabStatus('prinseq');

        // If PRINSEQ is running, show PRINSEQ tab
        if (prinseqStatus === 'running') {
            return 'prinseq';
        }

        // If Trimmomatic is running, show Trimmomatic tab
        if (trimmomaticStatus === 'running') {
            return 'trimmomatic';
        }

        // If PRINSEQ is completed but Trimmomatic is not, show PRINSEQ tab
        if (prinseqStatus === 'completed' && trimmomaticStatus !== 'completed') {
            return 'prinseq';
        }

        // Default to Trimmomatic tab
        return 'trimmomatic';
    };

    const [activeTab, setActiveTab] = useState<PreprocessingTab>(getInitialTab());
    const [userHasManuallySelected, setUserHasManuallySelected] = useState(false);

    // Update active tab when pipeline status changes (only if user hasn't manually selected)
    useEffect(() => {
        // Skip auto-switching if user has manually selected a tab
        if (userHasManuallySelected) {
            return;
        }

        const trimmomaticStatus = getTabStatus('trimmomatic');
        const prinseqStatus = getTabStatus('prinseq');

        // Auto-switch only if user hasn't manually intervened
        if (prinseqStatus === 'running' && activeTab !== 'prinseq') {
            setActiveTab('prinseq');
        } else if (trimmomaticStatus === 'running' && activeTab !== 'trimmomatic') {
            setActiveTab('trimmomatic');
        }
    }, [pipelineStatus, userHasManuallySelected, activeTab]); // Re-run when pipeline status changes

    const handleTabChange = (tab: PreprocessingTab) => {
        setActiveTab(tab);
        setUserHasManuallySelected(true); // Mark that user has manually selected a tab
    };

    const renderContent = () => {
        switch (activeTab) {
            case 'trimmomatic':
                return (
                    <WorkbenchDetailPreprocessingTrimmomatic
                        workbench={workbench}
                        pipelineStepsData={pipelineStepsData}
                    />
                );
            case 'prinseq':
                return (
                    <WorkbenchDetailPreprocessingPrinseq
                        workbench={workbench}
                        pipelineStepsData={pipelineStepsData}
                    />
                );
            default:
                return (
                    <WorkbenchDetailPreprocessingTrimmomatic
                        workbench={workbench}
                        pipelineStepsData={pipelineStepsData}
                    />
                );
        }
    };

    return (
        <div className="h-full flex flex-col">
            {/* Sub-tabs for Preprocessing */}
            <div className="border-b border-slate-200 bg-slate-50">
                <nav className="flex space-x-2 px-6">
                    <TabButton
                        label="Trimmomatic"
                        isActive={activeTab === 'trimmomatic'}
                        onClick={() => handleTabChange('trimmomatic')}
                        pipelineStatus={getTabStatus('trimmomatic')}
                        showProgress={true}
                    />
                    <TabButton
                        label="PRINSEQ"
                        isActive={activeTab === 'prinseq'}
                        onClick={() => handleTabChange('prinseq')}
                        pipelineStatus={getTabStatus('prinseq')}
                        showProgress={true}
                    />
                </nav>
            </div>

            {/* Content area */}
            <div className="flex-1 overflow-y-auto">
                {renderContent()}
            </div>
        </div>
    );
};

export default WorkbenchDetailPreprocessing;
