import React, { useState, useEffect } from 'react';
import { Workbench } from '../types';
import { apiService } from '../services/api';
import WorkbenchDetailDEGMatrixUp from './WorkbenchDetailDEGMatrixUp';
import WorkbenchDetailDEGMatrixDown from './WorkbenchDetailDEGMatrixDown';
import WorkbenchDetailDEGMA from './WorkbenchDetailDEGMA';
import WorkbenchDetailDEGVolcano from './WorkbenchDetailDEGVolcano';
import WorkbenchDetailDEGExpressionMatrix from './WorkbenchDetailDEGExpressionMatrix';
import WorkbenchDetailGSEA from './WorkbenchDetailGSEA';
import { VennSetSummary } from './VennSetMenu';

// ========================================
// Type Definitions
// ========================================

interface WorkbenchDetailDEGProps {
    workbench: Workbench;
    pipelineStepsData?: any[];
    selectedGenes: Set<string>;
    onSelectionChange: (genes: Set<string>) => void;
    onAnalysisRequest: (type: string) => void;
    showComingSoon: () => void;
    onNavigateToVennDiagram: (genes: string[], targetSetIndex?: number) => void;
    vennSetSummaries?: VennSetSummary[];
}

type DEGTab = 'matrix_up' | 'matrix_down' | 'ma_plot' | 'volcano_plot' | 'expression_matrix' | 'gsea';
type DEGStatus = 'pending' | 'running' | 'completed' | 'failed' | 'not_started' | 'insufficient_replicates';

// ========================================
// Main Component
// ========================================

const WorkbenchDetailDEG: React.FC<WorkbenchDetailDEGProps> = ({
    workbench,
    pipelineStepsData = [],
    selectedGenes,
    onSelectionChange,
    onAnalysisRequest,
    showComingSoon,
    onNavigateToVennDiagram,
    vennSetSummaries
}) => {
    const [activeTab, setActiveTab] = useState<DEGTab>('matrix_up');
    const [degStatus, setDegStatus] = useState<DEGStatus>('not_started');
    const [toolName, setToolName] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [comparisons, setComparisons] = useState<Array<{ name: string; tool_name: string }>>([]);
    const [selectedComparison, setSelectedComparison] = useState<string | null>(null);
    const [sampleStructure, setSampleStructure] = useState<Record<string, number>>({});
    const [comparisonSearch, setComparisonSearch] = useState('');
    const degStep = Array.isArray(pipelineStepsData)
        ? pipelineStepsData.find(step => step?.step === 'deg')
        : null;
    const isGSEAEnabledInPipeline = degStep?.parameters?.gsea_enabled !== false;
    const hasGSEAResults = Boolean(workbench?.has_gsea_results);
    const isGSEATabEnabled = isGSEAEnabledInPipeline || hasGSEAResults;

    useEffect(() => {
        if (activeTab === 'gsea' && !isGSEATabEnabled) {
            setActiveTab('matrix_up');
        }
    }, [activeTab, isGSEATabEnabled]);

    // DEG 파이프라인 상태 조회
    useEffect(() => {
        // workbench가 null이면 실행하지 않음
        if (!workbench || !workbench.id) {
            setIsLoading(false);
            return;
        }

        const fetchDEGProgress = async () => {
            try {
                setIsLoading(true);
                const response = await apiService.fetchDEGProgress(workbench.id);

                setDegStatus(response.status);
                setToolName(response.tool_name);
                setSampleStructure(response.sample_structure || {});

                // completed 상태이면 comparison 목록 조회
                if (response.status === 'completed') {
                    try {
                        const comparisonsData = await apiService.fetchDEGComparisons(workbench.id);
                        setComparisons(comparisonsData.comparisons);

                        // 첫 번째 comparison 자동 선택
                        if (comparisonsData.comparisons.length > 0 && !selectedComparison) {
                            setSelectedComparison(comparisonsData.comparisons[0].name);
                        }
                    } catch (error) {
                        console.error('Failed to fetch DEG comparisons:', error);
                    }
                }
            } catch (error) {
                console.error('Failed to fetch DEG progress:', error);
                setDegStatus('not_started');
            } finally {
                setIsLoading(false);
            }
        };

        fetchDEGProgress();

        // 5초마다 상태 업데이트 (running 상태일 때만)
        const intervalId = setInterval(() => {
            if (degStatus === 'running' || degStatus === 'pending') {
                fetchDEGProgress();
            }
        }, 5000);

        return () => clearInterval(intervalId);
    }, [workbench?.id, degStatus]);

    // 상태별 안내 화면 렌더링
    const renderStatusMessage = () => {
        console.log('');
        console.log('🎨 [DEG-RENDER] renderStatusMessage() called');
        console.log('   ├─ isLoading:', isLoading);
        console.log('   ├─ degStatus:', degStatus);
        console.log('   ├─ toolName:', toolName);
        console.log('   └─ sampleStructure:', sampleStructure);

        if (isLoading) {
            console.log('   └─ Rendering: Loading spinner');
            console.log('');
            return (
                <div className="flex items-center justify-center h-96">
                    <div className="text-center">
                        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 mb-4">
                            <svg className="animate-spin h-8 w-8 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        </div>
                        <h3 className="text-lg font-semibold text-slate-900 mb-2">Loading...</h3>
                        <p className="text-sm text-slate-600 max-w-md">Checking DEG analysis status...</p>
                    </div>
                </div>
            );
        }

        if (degStatus === 'running' || degStatus === 'pending') {
            console.log('   └─ Rendering: Analysis in Progress (status=' + degStatus + ')');
            console.log('');
            return (
                <div className="flex items-center justify-center h-96">
                    <div className="text-center">
                        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 mb-4">
                            <svg className="animate-spin h-8 w-8 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        </div>
                        <h3 className="text-lg font-semibold text-slate-900 mb-2">Analysis in Progress</h3>
                        <p className="text-sm text-slate-600 max-w-md">
                            DEG analysis using {toolName || 'unknown tool'} is currently running. Please wait for completion...
                        </p>
                    </div>
                </div>
            );
        }

        if (degStatus === 'failed') {
            console.log('   └─ Rendering: Analysis Failed');
            console.log('');
            return (
                <div className="flex items-center justify-center h-96">
                    <div className="text-center">
                        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-red-100 mb-4">
                            <svg className="h-8 w-8 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                        </div>
                        <h3 className="text-lg font-semibold text-slate-900 mb-2">Analysis Failed</h3>
                        <p className="text-sm text-slate-600 max-w-md">
                            DEG analysis failed. Please check the pipeline logs or try rerunning the analysis.
                        </p>
                    </div>
                </div>
            );
        }

        if (degStatus === 'not_started') {
            console.log('   └─ Rendering: No DEG Results Available (status="not_started")');
            console.log('');
            return (
                <div className="flex items-center justify-center h-96">
                    <div className="text-center">
                        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-100 mb-4">
                            <svg className="h-8 w-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                        </div>
                        <h3 className="text-lg font-semibold text-slate-900 mb-2">No DEG Results Available</h3>
                        <p className="text-sm text-slate-600 max-w-md">DEG analysis has not been performed yet.</p>
                        <p className="text-sm text-slate-500 mt-4">Please run the DEG analysis step in the pipeline first.</p>
                    </div>
                </div>
            );
        }

        if (degStatus === 'insufficient_replicates') {
            console.log('   └─ Rendering: Insufficient Replicates Warning (status="insufficient_replicates")');
            console.log('');
            const sampleStructureText = Object.entries(sampleStructure)
                .map(([group, count]) => `${group} (${count})`)
                .join(', ');

            return (
                <div className="flex items-center justify-center h-96">
                    <div className="max-w-2xl w-full bg-amber-50 border-2 border-amber-200 rounded-xl p-8">
                        <div className="flex items-start">
                            <svg className="w-12 h-12 text-amber-500 mr-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                            <div className="flex-1">
                                <h3 className="text-xl font-bold text-amber-900 mb-3">
                                    ⚠️ Insufficient Replicates for DESeq2 Analysis
                                </h3>
                                <div className="space-y-3 text-amber-800">
                                    <p className="text-base">
                                        DESeq2 requires at least <span className="font-semibold">2 biological replicates per group</span> for differential expression analysis.
                                    </p>
                                    <p className="text-base">
                                        Current sample structure: <span className="font-semibold">{sampleStructureText}</span>
                                    </p>
                                    <div className="mt-4 pt-4 border-t border-amber-300">
                                        <p className="text-sm text-amber-700 font-semibold mb-2">
                                            Recommendations:
                                        </p>
                                        <ul className="text-sm text-amber-700 list-disc list-inside space-y-1">
                                            <li>Add more biological replicates to each group (minimum 2 per group)</li>
                                            <li>Use edgeR instead, which can handle experiments with fewer replicates using exact tests</li>
                                            <li>Consider using the <span className="font-mono">--dispersion</span> parameter if you must proceed (not recommended for publication)</li>
                                        </ul>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            );
        }

        return null;
    };

    // 탭 렌더링
    const renderTabContent = () => {
        // workbench가 null이면 로딩 메시지 표시
        if (!workbench || !workbench.id) {
            return (
                <div className="flex items-center justify-center h-96">
                    <p className="text-slate-500">Loading workbench information...</p>
                </div>
            );
        }

        // Expression Matrix 탭은 comparison 불필요
        if (activeTab === 'expression_matrix') {
            return (
                <WorkbenchDetailDEGExpressionMatrix
                    workbenchId={workbench.id}
                    selectedGenes={selectedGenes}
                    onSelectionChange={onSelectionChange}
                    onAnalysisRequest={onAnalysisRequest}
                    showComingSoon={showComingSoon}
                    onNavigateToVennDiagram={onNavigateToVennDiagram}
                    vennSetSummaries={vennSetSummaries}
                />
            );
        }

        // 다른 탭들은 comparison 필요
        if (!selectedComparison) {
            return (
                <div className="flex items-center justify-center h-96">
                    <p className="text-slate-500">Please select a comparison from the sidebar.</p>
                </div>
            );
        }

        switch (activeTab) {
            case 'matrix_up':
                return (
                    <WorkbenchDetailDEGMatrixUp
                        workbenchId={workbench.id}
                        comparisonName={selectedComparison}
                        toolName={toolName || 'edgeR'}
                        selectedGenes={selectedGenes}
                        onSelectionChange={onSelectionChange}
                        onAnalysisRequest={onAnalysisRequest}
                        showComingSoon={showComingSoon}
                        onNavigateToVennDiagram={onNavigateToVennDiagram}
                        vennSetSummaries={vennSetSummaries}
                    />
                );
            case 'matrix_down':
                return (
                    <WorkbenchDetailDEGMatrixDown
                        workbenchId={workbench.id}
                        comparisonName={selectedComparison}
                        toolName={toolName || 'edgeR'}
                        selectedGenes={selectedGenes}
                        onSelectionChange={onSelectionChange}
                        onAnalysisRequest={onAnalysisRequest}
                        showComingSoon={showComingSoon}
                        onNavigateToVennDiagram={onNavigateToVennDiagram}
                        vennSetSummaries={vennSetSummaries}
                    />
                );
            case 'ma_plot':
                return (
                    <WorkbenchDetailDEGMA
                        workbenchId={workbench.id}
                        comparisonName={selectedComparison}
                        toolName={toolName || 'edgeR'}
                        selectedGenes={selectedGenes}
                        onSelectionChange={onSelectionChange}
                        onAnalysisRequest={onAnalysisRequest}
                        showComingSoon={showComingSoon}
                    />
                );
            case 'volcano_plot':
                return (
                    <WorkbenchDetailDEGVolcano
                        workbenchId={workbench.id}
                        comparisonName={selectedComparison}
                        toolName={toolName || 'edgeR'}
                        selectedGenes={selectedGenes}
                        onSelectionChange={onSelectionChange}
                        onAnalysisRequest={onAnalysisRequest}
                        showComingSoon={showComingSoon}
                    />
                );
            case 'gsea':
                return (
                    <WorkbenchDetailGSEA
                        workbench={workbench}
                        workbenchId={workbench.id}
                        comparisonName={selectedComparison}
                        toolName={toolName || 'edgeR'}
                        selectedGenes={selectedGenes}
                        onSelectionChange={onSelectionChange}
                        onAnalysisRequest={onAnalysisRequest}
                        showComingSoon={showComingSoon}
                        onNavigateToVennDiagram={onNavigateToVennDiagram}
                        vennSetSummaries={vennSetSummaries}
                    />
                );
            default:
                return null;
        }
    };

    const tabs: { id: DEGTab; label: string; icon: React.ReactNode }[] = [
        {
            id: 'matrix_up',
            label: 'Matrix (Up)',
            icon: (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                </svg>
            )
        },
        {
            id: 'matrix_down',
            label: 'Matrix (Down)',
            icon: (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                </svg>
            )
        },
        {
            id: 'ma_plot',
            label: 'MA Plot',
            icon: (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
            )
        },
        {
            id: 'volcano_plot',
            label: 'Volcano Plot',
            icon: (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                </svg>
            )
        },
        {
            id: 'expression_matrix',
            label: 'Expression Matrix',
            icon: (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
            )
        },
        {
            id: 'gsea',
            label: 'GSEA',
            icon: (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 19h16M6 16l3-5 3 2 4-6 2 3" />
                </svg>
            )
        }
    ];

    return (
        <div className="h-full p-6">
            <div className="bg-white rounded-lg shadow-sm border border-slate-200 h-full">
                <div className="p-6 h-full flex flex-col">
                    <div className="flex items-center space-x-4 mb-6">
                        <h3 className="text-lg font-semibold text-slate-900">Differential Expression Analysis</h3>
                        {toolName && (
                            <span className="px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-sm font-medium">
                                {toolName.toUpperCase()}
                            </span>
                        )}
                    </div>

                    {/* 상태별 메시지 표시 또는 탭 UI */}
                    {degStatus !== 'completed' ? (
                        renderStatusMessage()
                    ) : (
                        <div className="flex flex-1 min-h-0 space-x-6">
                            {/* 왼쪽 사이드바: Comparison 선택 (Expression Matrix 탭에서는 숨김) */}
                            {activeTab !== 'expression_matrix' && (
                                <div className="w-64 flex-shrink-0 border-r border-slate-200 pr-6 flex flex-col min-h-0">
                                    <h4 className="text-sm font-semibold text-slate-700 mb-3">Comparisons</h4>
                                    {/* 검색창 */}
                                    <div className="relative mb-3">
                                        <input
                                            type="text"
                                            value={comparisonSearch}
                                            onChange={e => setComparisonSearch(e.target.value)}
                                            placeholder="Search comparisons..."
                                            className="w-full pl-8 pr-7 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary"
                                        />
                                        <svg className="absolute left-2.5 top-2 h-4 w-4 text-slate-400 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                        </svg>
                                        {comparisonSearch && (
                                            <button
                                                onClick={() => setComparisonSearch('')}
                                                className="absolute right-2 top-1.5 text-slate-400 hover:text-slate-600"
                                            >
                                                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                                </svg>
                                            </button>
                                        )}
                                    </div>
                                    <div className="space-y-2 overflow-y-auto flex-1">
                                        {comparisons
                                            .filter(c =>
                                                !comparisonSearch ||
                                                c.name.toLowerCase().replace(/_/g, ' ').includes(comparisonSearch.toLowerCase())
                                            )
                                            .map((comparison) => (
                                                <button
                                                    key={comparison.name}
                                                    onClick={() => {
                                                        setSelectedComparison(comparison.name);
                                                        onSelectionChange(new Set());
                                                    }}
                                                    className={`
                                                        w-full text-left px-4 py-3 rounded-lg text-sm transition-colors
                                                        ${selectedComparison === comparison.name
                                                            ? 'bg-primary text-white font-semibold'
                                                            : 'bg-slate-50 text-slate-700 hover:bg-slate-100'
                                                        }
                                                    `}
                                                >
                                                    <div className="font-semibold">{comparison.name.replace(/_/g, ' ')}</div>
                                                    <div className={`text-xs mt-1 ${selectedComparison === comparison.name ? 'text-white/80' : 'text-slate-500'}`}>
                                                        {comparison.tool_name}
                                                    </div>
                                                </button>
                                            ))
                                        }
                                        {comparisonSearch && comparisons.filter(c =>
                                            c.name.toLowerCase().replace(/_/g, ' ').includes(comparisonSearch.toLowerCase())
                                        ).length === 0 && (
                                            <p className="text-xs text-slate-400 text-center py-4">No matches found</p>
                                        )}
                                    </div>
                                </div>
                            )}

                            {/* 오른쪽 컨텐츠: 탭 + 데이터 */}
                            <div className="flex-1 flex flex-col min-w-0">
                                {/* 탭 네비게이션 */}
                                <div className="border-b border-slate-200 mb-6">
                                    <nav className="-mb-px flex space-x-8">
                                        {tabs.map(tab => {
                                            const isDisabled = tab.id === 'gsea' && !isGSEATabEnabled;
                                            return (
                                            <button
                                                key={tab.id}
                                                onClick={() => {
                                                    if (isDisabled) return;
                                                    setActiveTab(tab.id);
                                                    // 탭 전환 시 선택된 유전자 초기화
                                                    onSelectionChange(new Set());
                                                }}
                                                disabled={isDisabled}
                                                title={isDisabled ? 'GSEA is disabled until the pipeline enables it or prior GSEA results exist.' : undefined}
                                                className={`
                                                    flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors
                                                    ${activeTab === tab.id
                                                        ? 'border-primary text-primary'
                                                        : isDisabled
                                                        ? 'border-transparent text-slate-300 cursor-not-allowed'
                                                        : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                                                    }
                                                `}
                                            >
                                                {tab.icon}
                                                <span>{tab.label}</span>
                                            </button>
                                        )})}
                                    </nav>
                                </div>

                                {/* 탭 컨텐츠 */}
                                <div className="flex-1 overflow-auto">
                                    {renderTabContent()}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default WorkbenchDetailDEG;
