
import React, { useState, useMemo, useRef, useEffect } from 'react';
import { PipelineJobStatus, StepDetail } from '../types';
import useWebSocket from '../src/hooks/useWebSocket';  // WebSocket Hook 추가
import WorkbenchDetailOverview from '../components/WorkbenchDetailOverview';
import WorkbenchDetailRawData from '../components/WorkbenchDetailRawData';
import WorkbenchDetailQC from '../components/WorkbenchDetailQC';
import WorkbenchDetailPreprocessing from '../components/WorkbenchDetailPreprocessing';
import WorkbenchDetailAlignment from '../components/WorkbenchDetailAlignment';
import WorkbenchDetailCounts from '../components/WorkbenchDetailCounts';
import WorkbenchDetailDEG from '../components/WorkbenchDetailDEG';
import WorkbenchDetailPCA from './WorkbenchDetailPCA';
import WorkbenchDetailClustering from './WorkbenchDetailClustering';
import WorkbenchDetailHeatmap from '../components/WorkbenchDetailHeatmap';
import WorkbenchDetailVennDiagram from '../components/WorkbenchDetailVennDiagram';
import { VennSetSummary, VENN_SET_COLORS } from '../components/VennSetMenu';

// Hook for calculating dynamic table height
const useTableHeight = () => {
    const [tableHeight, setTableHeight] = useState('60vh');
    
    useEffect(() => {
        const calculateHeight = () => {
            const viewportHeight = window.innerHeight;
            const headerHeight = 120; // Approximate header height
            const tabsHeight = 60;    // Approximate tabs height
            const paddingHeight = 100; // Additional padding and margins
            const toolbarHeight = 80; // Toolbar with search and filters
            
            const availableHeight = viewportHeight - headerHeight - tabsHeight - paddingHeight - toolbarHeight;
            const minHeight = Math.max(300, availableHeight);
            const maxHeight = Math.min(viewportHeight * 0.8, minHeight);
            
            setTableHeight(`${maxHeight}px`);
        };
        
        calculateHeight();
        window.addEventListener('resize', calculateHeight);
        
        return () => window.removeEventListener('resize', calculateHeight);
    }, []);
    
    return tableHeight;
};
import * as d3 from 'd3';
import { Workbench, WorkbenchTab } from '../types';
import StatusBadge from '../components/StatusBadge';
import Modal from '../components/Modal';
import DeleteWorkbenchModal from '../components/DeleteWorkbenchModal';
import { apiService } from '../services/api';

interface WorkbenchDetailProps {
  workbenchId: number;
  activeTab: WorkbenchTab;
  showComingSoon: () => void;
  onNavigateToTab?: (tab: WorkbenchTab) => void;
  onNavigateToDashboard?: () => void;
}

// Tab navigation removed - now handled by Sidebar









export default function WorkbenchDetail({
  workbenchId,
  activeTab,
  showComingSoon,
  onNavigateToTab,
  onNavigateToDashboard
}: WorkbenchDetailProps): React.ReactNode {
  const [workbenchData, setWorkbenchData] = useState<any>(null);
  const [pipelineConfig, setPipelineConfig] = useState<any>(null);
  const [pipelineStepsData, setPipelineStepsData] = useState<any[]>([]);
  const [samples, setSamples] = useState<any[]>([]);
  const [fileMappings, setFileMappings] = useState<any[]>([]);
  const [executedStepNames, setExecutedStepNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Delete modal state
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Start Analysis modal state
  const [showStartAnalysisModal, setShowStartAnalysisModal] = useState(false);
  const [selectedGenes, setSelectedGenes] = useState<Set<string>>(new Set());
  const [heatmaps, setHeatmaps] = useState<{title: string, genes: string[]}[]>([]);
  
  // Pipeline status state
  const [pipelineStatus, setPipelineStatus] = useState<PipelineJobStatus | null>(null);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [pipelineSteps, setPipelineSteps] = useState<Record<string, StepDetail>>({});
  const [isHeatmapModalOpen, setHeatmapModalOpen] = useState(false);
  const [heatmapTitle, setHeatmapTitle] = useState('');
  const [heatmapColors, setHeatmapColors] = useState({
      down: '#0000ff',
      mid: '#ffffff',
      up: '#ff0000'
  });

  // Venn diagram Sets state (persists across tab changes)
  const [vennGeneSets, setVennGeneSets] = useState<Array<{id: string, name: string, genes: string[]}>>([]);
  const [vennGeneInputs, setVennGeneInputs] = useState<{ [key: string]: string }>({});

  // Venn diagram toast notification
  const [vennToast, setVennToast] = useState<{
    targetSetIndex: number;
    targetSetName: string;
    selectedGeneCount: number;
    totalCount: number;
    sets: VennSetSummary[];
  } | null>(null);
  const vennToastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fetch detailed workbench data from API (extracted as useCallback for reuse)
  const fetchWorkbenchDetail = React.useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/workbenches/${workbenchId}`, {
        credentials: 'include'
      });

      if (!response.ok) {
        throw new Error('Failed to fetch workbench details');
      }

      const data = await response.json();

      setWorkbenchData(data.workbench);
      setPipelineConfig(data.pipeline_config);
      setPipelineStepsData(data.pipeline_steps || []);
      setSamples(data.samples || []);
      setFileMappings(data.sample_file_mappings || []);  // Using sample_file_mappings
      setExecutedStepNames(data.executed_step_names || []);  // 실제 실행된 단계 이름 목록

      // Set pipeline status from API response
      if (data.pipeline_status) {
        setPipelineStatus(data.pipeline_status);
        console.log('📊 [WORKBENCH-DETAIL] Pipeline status loaded:', data.pipeline_status.status);
      } else {
        setPipelineStatus(null);
        console.log('📊 [WORKBENCH-DETAIL] No pipeline status available');
      }

      // Check for currently running job and start polling
      if (data.current_job_id) {
        setCurrentJobId(data.current_job_id);
        // The polling will start automatically via the useEffect when currentJobId changes
      } else {
        setCurrentJobId(null); // Clear any previous workbench's job ID to stop stale polling
        console.log('ℹ️ No running job found for this workbench');
      }

      setError(null);
    } catch (err) {
      console.error('Error fetching workbench details:', err);
      setError('Failed to load workbench details');
    } finally {
      setLoading(false);
    }
  }, [workbenchId]);

  // Fetch workbench details on mount or when workbenchId changes
  useEffect(() => {
    if (workbenchId) {
      fetchWorkbenchDetail();
    }
  }, [workbenchId, fetchWorkbenchDetail]);


  // Poll pipeline status for real-time updates
  useEffect(() => {
    if (!currentJobId) return;
    
    let pollInterval: NodeJS.Timeout;
    
    const fetchPipelineStatus = async () => {
      try {
        const status = await apiService.getPipelineJobStatus(currentJobId);
        
        setPipelineStatus(status);
        
        // Update pipeline steps mapping for tab indicators
        const stepsMap: Record<string, StepDetail> = {};
        status.steps.forEach(step => {
          stepsMap[step.step_id] = step;
        });
        setPipelineSteps(stepsMap);
        
        // Stop polling if pipeline is completed or failed
        if (status.status === 'completed' || status.status === 'failed') {
          if (pollInterval) {
            clearInterval(pollInterval);
          }
          setCurrentJobId(null); // Clear job ID to stop polling
        }
      } catch (error: any) {
        console.error('Failed to fetch pipeline status:', error);
        
        // 특별히 job이 삭제된 경우 (404 with shouldStopPolling) polling 중단
        if (error?.shouldStopPolling || error?.status === 404) {
          console.log(`🛑 Pipeline job ${currentJobId} deleted or not found - stopping polling`);
          if (pollInterval) {
            clearInterval(pollInterval);
          }
          setCurrentJobId(null);
          return;
        }
        
        // 다른 에러는 임시적일 수 있으므로 polling 계속
        console.log('⏳ Continuing polling despite error (might be temporary)');
      }
    };

    // Start polling immediately, then every 3 seconds
    fetchPipelineStatus();
    pollInterval = setInterval(fetchPipelineStatus, 3000);

    return () => {
      if (pollInterval) {
        clearInterval(pollInterval);
      }
    };
  }, [currentJobId]);
  
  const mainContentRef = useRef(null);
  
  useEffect(() => {
    
    if (activeTab === 'heatmap' && mainContentRef.current) {
      const element = mainContentRef.current;
    }
  }, [activeTab]);

  const handleAnalysisRequest = (type: 'heatmap' | 'go') => {
      if (type === 'heatmap') {
          setHeatmapTitle(`Heatmap of ${selectedGenes.size} genes`);
          setHeatmapModalOpen(true);
      } else {
          showComingSoon();
      }
  };

  // Helper function to get pipeline step status for tabs
  const getTabStatus = (stepId: string): PipelineStepStatus | undefined => {
      const step = pipelineSteps[stepId];
      if (!step) return undefined;
      return step.status;
  };

  const handleStartAnalysis = () => {
    console.log('=== Start Analysis Debug ===');
    console.log('workbenchData:', workbenchData);
    console.log('workbenchData?.workbench:', workbenchData?.workbench);
    console.log('workbenchData?.workbench?.id:', workbenchData?.workbench?.id);

    // Try both possible data structures
    const workbenchId = workbenchData?.workbench?.id || workbenchData?.id;

    if (!workbenchId) {
      console.error('Cannot find workbench information. workbenchData structure:', JSON.stringify(workbenchData, null, 2));
      alert('Cannot find workbench information.');
      return;
    }

    // Show modal instead of window.confirm
    setShowStartAnalysisModal(true);
  };

  const handleConfirmStartAnalysis = async () => {
    const workbenchId = workbenchData?.workbench?.id || workbenchData?.id;
    const workbenchName = workbenchData?.workbench?.name || workbenchData?.name;

    try {
      console.log('🚀 Starting pipeline job creation...');
      console.log('Workbench ID:', workbenchId);
      console.log('Workbench Name:', workbenchName);
      
      // Dynamic import to handle potential missing API
      const { apiService } = await import('../services/api');
      
      const response = await apiService.createPipelineJob(workbenchId);
      console.log('✅ Pipeline job created successfully:', response);
      
      // Start pipeline status polling
      setCurrentJobId(response.job_id);

      // Close modal
      setShowStartAnalysisModal(false);

      alert(
        `Pipeline analysis has been successfully started!\n\n` +
        `Job ID: ${response.job_id}\n` +
        `Workbench: ${response.workbench_name}\n\n` +
        'You can monitor the analysis progress in real-time.'
      );

    } catch (error: any) {
      console.error('❌ Pipeline job creation failed:', error);
      console.error('Error details:', {
        status: error.status,
        message: error.message,
        stack: error.stack
      });
      
      let errorMessage = 'Failed to start pipeline.';
      
      if (error.status === 503) {
        console.error('🚨 Service unavailable - Missing dependencies');
        errorMessage = 
          'Pipeline management system is currently unavailable.\n\n' +
          'Please contact the administrator or run the following command:\n' +
          'pip install psutil';
      } else if (error.message) {
        errorMessage += '\n\nError: ' + error.message;
      }
      
      alert(errorMessage);
      console.error('Full error object:', JSON.stringify(error, null, 2));
    }
  };

  // Stop analysis handler
  const handleStopAnalysis = async () => {
    const workbenchId = workbenchData?.workbench?.id || workbenchData?.id;
    const workbenchName = workbenchData?.workbench?.name || workbenchData?.name;
    
    if (!workbenchId) {
      console.error('워크벤치 정보를 찾을 수 없습니다.');
      alert('워크벤치 정보를 찾을 수 없습니다.');
      return;
    }

    const confirmStop = window.confirm(
      `Stop RNA-seq analysis for "${workbenchName}" workbench?\n\n` +
      'All running tasks will be terminated and queued tasks will be cancelled.\n' +
      'Results from completed steps will be preserved.'
    );

    if (!confirmStop) return;

    try {
      console.log(`🛑 Stopping analysis for workbench ${workbenchId}...`);
      
      const result = await apiService.stopAnalysis(workbenchId);
      
      console.log('✅ Stop analysis result:', result);
      
      if (result.success) {
        // 성공적으로 중지된 경우
        alert(
          `Analysis has been successfully stopped.\n\n` +
          `Stopped jobs: ${result.stopped_jobs}\n` +
          `Stopped workers: ${result.stopped_workers}`
        );
        
        // 폴링 중지 및 상태 초기화
        setCurrentJobId(null);
        setPipelineStatus(null);
        
      } else {
        throw new Error(result.message || 'Analysis stop failed');
      }
      
    } catch (error: any) {
      console.error('Stop analysis failed:', error);
      
      let errorMessage = 'Failed to stop analysis.';
      if (error.message) {
        errorMessage += '\n\nError: ' + error.message;
      }
      
      alert(errorMessage);
    }
  };

  // Open delete confirmation modal
  const handleDeleteWorkbench = () => {
    setShowDeleteModal(true);
  };

  // Handle actual deletion with options
  const handleConfirmDelete = async (deleteRawData: boolean) => {
    console.log('=== Delete Workbench Debug ===');
    console.log('deleteRawData:', deleteRawData);
    console.log('workbenchData:', workbenchData);
    
    // Try both possible data structures
    const workbenchId = workbenchData?.workbench?.id || workbenchData?.id;
    const workbenchName = workbenchData?.workbench?.name || workbenchData?.name;
    
    if (!workbenchId) {
      console.error('Cannot find workbench information. workbenchData structure:', JSON.stringify(workbenchData, null, 2));
      alert('Cannot find workbench information.');
      return;
    }

    setIsDeleting(true);

    try {
      const { apiService } = await import('../services/api');
      
      const response = await apiService.deleteWorkbench(workbenchId, deleteRawData);
      
      // 중요: 워크벤치 삭제 후 관련 polling 즉시 중단
      console.log('🛑 Workbench deleted - stopping all polling...');
      
      // Job status polling 중단
      if (currentJobId) {
        console.log(`🛑 Stopping pipeline job polling for ${currentJobId}`);
        setCurrentJobId(null);
      }
      
      
      setShowDeleteModal(false);
      
      // Show success message based on deletion type
      const message = deleteRawData 
        ? `Workbench "${workbenchName}" has been completely deleted along with all data.`
        : `Workbench "${workbenchName}" has been deleted. Only the original Raw Data files are preserved on the server.`;
      
      alert(message);
      
      // Both deletion types navigate back to dashboard (workbench is deleted in both cases)
      if (onNavigateToDashboard) {
        onNavigateToDashboard();
      } else if (window.history.length > 1) {
        window.history.back();
      } else {
        // Fallback - stay on current page and show error
        console.warn('No navigation callback provided and no history available');
      }
      
    } catch (error: any) {
      setIsDeleting(false);
      
      let errorMessage = 'Failed to delete workbench.';
      
      if (error.status === 400 && error.message.includes('running pipeline jobs')) {
        errorMessage = 
          'Cannot delete workbench because there are running pipeline jobs.\n\n' +
          'Please stop the pipeline jobs first or wait until they are completed.';
      } else if (error.message) {
        errorMessage += '\n\nError: ' + error.message;
      }
      
      alert(errorMessage);
      console.error('Workbench deletion failed:', error);
    }
  };

  const handleCreateHeatmap = () => {
    if (!heatmapTitle.trim() || selectedGenes.size === 0) return;
    const newHeatmap = {
        title: heatmapTitle,
        genes: Array.from(selectedGenes),
    };
    setHeatmaps(prev => [...prev, newHeatmap]);
    setHeatmapModalOpen(false);
    setHeatmapTitle('');
    setSelectedGenes(new Set());
    // Navigation to heatmap tab is now handled by Sidebar
  };

  const MAX_VENN_SETS = 4;

  const vennSetSummaries = useMemo<VennSetSummary[]>(() => {
    return Array.from({ length: MAX_VENN_SETS }, (_, index) => {
      const existingSet = vennGeneSets[index];
      const dedupedGenes = Array.from(new Set(existingSet?.genes || []));
      return {
        index,
        name: existingSet?.name?.trim() || `Set ${String.fromCharCode(65 + index)}`,
        count: dedupedGenes.length,
        isEmpty: dedupedGenes.length === 0,
      };
    });
  }, [vennGeneSets]);

  // Handle navigate to Venn Diagram with gene list
  const handleNavigateToVennDiagram = (genes: string[], targetSetIndex?: number) => {
    const normalizedGenes = Array.from(new Set(genes.filter(Boolean)));
    if (normalizedGenes.length === 0) return;

    const nextSetIndex = typeof targetSetIndex === 'number'
      ? Math.max(0, Math.min(MAX_VENN_SETS - 1, targetSetIndex))
      : vennGeneSets.length;

    if (typeof targetSetIndex !== 'number' && nextSetIndex >= MAX_VENN_SETS) {
      alert(`Maximum ${MAX_VENN_SETS} sets allowed. Please clear or delete existing sets before adding new ones.`);
      return;
    }

    setVennGeneSets(prev => {
      const updatedSets = [...prev];

      while (updatedSets.length <= nextSetIndex) {
        const index = updatedSets.length;
        updatedSets.push({
          id: `set-${String.fromCharCode(97 + index)}`,
          name: `Set ${String.fromCharCode(65 + index)}`,
          genes: [],
        });
      }

      const currentTarget = updatedSets[nextSetIndex];
      const mergedGenes = Array.from(new Set([...(currentTarget?.genes || []), ...normalizedGenes]));
      updatedSets[nextSetIndex] = {
        ...currentTarget,
        genes: mergedGenes,
      };

      const updatedSummaries = Array.from({ length: MAX_VENN_SETS }, (_, index) => {
        const existingSet = updatedSets[index];
        const dedupedGenes = Array.from(new Set(existingSet?.genes || []));
        return {
          index,
          name: existingSet?.name?.trim() || `Set ${String.fromCharCode(65 + index)}`,
          count: dedupedGenes.length,
          isEmpty: dedupedGenes.length === 0,
        };
      });

      if (vennToastTimerRef.current) clearTimeout(vennToastTimerRef.current);
      setVennToast({
        targetSetIndex: nextSetIndex,
        targetSetName: updatedSummaries[nextSetIndex].name,
        selectedGeneCount: normalizedGenes.length,
        totalCount: updatedSummaries[nextSetIndex].count,
        sets: updatedSummaries,
      });
      vennToastTimerRef.current = setTimeout(() => setVennToast(null), 6000);

      setVennGeneInputs(prevInputs => {
        const nextInputs = { ...prevInputs };
        updatedSets.forEach((set) => {
          nextInputs[set.id] = Array.from(new Set(set.genes || [])).join('\n');
        });
        return nextInputs;
      });

      return updatedSets;
    });
  };

  // Handle reset Venn diagram Sets
  const handleResetVennSets = () => {
    setVennGeneSets([]);
    setVennGeneInputs({});
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'overview': return loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin w-8 h-8 border-4 border-primary border-t-transparent rounded-full"></div>
          <span className="ml-3 text-slate-600">Loading workbench details...</span>
        </div>
      ) : error ? (
        <div className="text-center py-12">
          <div className="text-red-500 mb-2">⚠️</div>
          <p className="text-slate-600 mb-4">{error}</p>
        </div>
      ) : (
        <WorkbenchDetailOverview
          workbench={workbenchData}
          pipelineConfig={pipelineConfig}
          pipelineStepsData={pipelineStepsData}
          onStartAnalysis={handleStartAnalysis}
          onDeleteWorkbench={handleDeleteWorkbench}
          showComingSoon={showComingSoon}
          pipelineStatus={pipelineStatus}
          onStopAnalysis={handleStopAnalysis}
          onRefreshData={fetchWorkbenchDetail}
        />
      );
      case 'rawdata':
        return (
          <WorkbenchDetailRawData
            workbench={workbenchData}
            samples={samples}
            fileMappings={fileMappings}
            pipelineStepsData={pipelineStepsData}
          />
        );
      case 'qc': return <WorkbenchDetailQC workbench={workbenchData} pipelineStepsData={pipelineStepsData} executedStepNames={executedStepNames} />;
      case 'preprocessing': return <WorkbenchDetailPreprocessing workbench={workbenchData} pipelineStepsData={pipelineStepsData} pipelineStatus={pipelineStatus} />;
      case 'alignment': return <WorkbenchDetailAlignment workbench={workbenchData} pipelineStepsData={pipelineStepsData} />;
      case 'count': return <WorkbenchDetailCounts workbench={workbenchData} pipelineStepsData={pipelineStepsData} selectedGenes={selectedGenes} onSelectionChange={setSelectedGenes} onAnalysisRequest={handleAnalysisRequest} showComingSoon={showComingSoon} onNavigateToVennDiagram={handleNavigateToVennDiagram} vennSetSummaries={vennSetSummaries} />;
      case 'deg': return <WorkbenchDetailDEG workbench={workbenchData} pipelineStepsData={pipelineStepsData} selectedGenes={selectedGenes} onSelectionChange={setSelectedGenes} onAnalysisRequest={handleAnalysisRequest} showComingSoon={showComingSoon} onNavigateToVennDiagram={handleNavigateToVennDiagram} vennSetSummaries={vennSetSummaries} />;
      case 'pca': return <WorkbenchDetailPCA workbenchId={workbenchId} />;
      case 'clustering': return <WorkbenchDetailClustering workbench={workbenchData} onNavigateToVennDiagram={handleNavigateToVennDiagram} vennSetSummaries={vennSetSummaries} />;
      case 'heatmap': return <WorkbenchDetailHeatmap workbenchId={workbenchId} />;
      case 'venndiagram': return <WorkbenchDetailVennDiagram workbenchId={workbenchId} hasTPMMatrix={workbenchData?.has_tpm_matrix !== false} geneSets={vennGeneSets} geneInputs={vennGeneInputs} onGeneSetsChange={setVennGeneSets} onGeneInputsChange={setVennGeneInputs} onReset={handleResetVennSets} />;
      default: return null;
    }
  }

  return (
    <div className="h-full flex flex-col p-4 min-h-0">
      {/* Venn Diagram Toast Notification */}
      {vennToast && (
        <div className="fixed top-4 right-4 z-50 bg-white rounded-lg shadow-xl border border-green-200 p-4 w-72 animate-fade-in">
          <div className="flex items-start gap-3">
            <svg className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-slate-800">
                Added to {vennToast.targetSetName}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {vennToast.selectedGeneCount.toLocaleString()} selected genes added. Total: {vennToast.totalCount.toLocaleString()}
              </p>
              <div className="mt-2 space-y-1">
                {vennToast.sets.map(s => (
                  <div key={s.name} className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2">
                      <span className={`h-2.5 w-2.5 rounded-full ${s.isEmpty ? 'bg-slate-300' : VENN_SET_COLORS[s.index].dot}`} />
                      <span className={s.index === vennToast.targetSetIndex ? `font-semibold ${VENN_SET_COLORS[s.index].text}` : 'text-slate-600'}>
                        {s.name}
                      </span>
                    </span>
                    <span className={s.index === vennToast.targetSetIndex ? `font-semibold ${VENN_SET_COLORS[s.index].text}` : 'text-slate-400'}>
                      {s.count.toLocaleString()} genes
                    </span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-xs text-slate-400">Go to Venn Diagram tab to view</p>
            </div>
            <button
              onClick={() => setVennToast(null)}
              className="text-slate-400 hover:text-slate-600 flex-shrink-0"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Start Analysis Modal */}
      <Modal
        isOpen={showStartAnalysisModal}
        onClose={() => setShowStartAnalysisModal(false)}
        title={`Start RNA-seq Analysis`}
      >
        <div className="space-y-4">
          <p className="text-slate-700">
            Start RNA-seq analysis for <span className="font-semibold">"{workbenchData?.workbench?.name || workbenchData?.name}"</span> workbench?
          </p>

          <div className="bg-slate-50 p-4 rounded-lg">
            <p className="text-sm font-semibold text-slate-700 mb-3">The analysis will proceed with the following steps:</p>
            <ol className="space-y-2">
              {pipelineStepsData.map((step, index) => (
                <li key={step.step || index} className="text-sm text-slate-600 flex items-start">
                  <span className="font-semibold text-primary mr-2">{index + 1}.</span>
                  <div>
                    <span className="font-medium">{step.description || step.step}</span>
                    <span className="text-slate-500 ml-2">({step.tool === 'trimmomatic_prinseq' ? 'Trimmomatic → PRINSEQ' : step.tool})</span>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>

        <div className="mt-6 flex justify-end space-x-3">
          <button
            onClick={() => setShowStartAnalysisModal(false)}
            className="px-4 py-2 text-sm font-semibold bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirmStartAnalysis}
            className="px-4 py-2 text-sm font-semibold bg-primary text-white rounded-lg hover:bg-primary-dark"
          >
            Start Analysis
          </button>
        </div>
      </Modal>

      <Modal
        isOpen={isHeatmapModalOpen}
        onClose={() => setHeatmapModalOpen(false)}
        title="Create New Heatmap"
      >
        <div className="space-y-4">
            <div>
                <label htmlFor="heatmapTitle" className="block text-sm font-medium text-slate-700 mb-1">Heatmap Title</label>
                <input
                    type="text"
                    id="heatmapTitle"
                    value={heatmapTitle}
                    onChange={e => setHeatmapTitle(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-primary focus:border-primary"
                    placeholder="Enter a title for your heatmap"
                />
            </div>
            <p className="text-sm text-slate-500">This will generate a heatmap for the {selectedGenes.size} selected genes.</p>
        </div>
        <div className="mt-6 flex justify-end space-x-3">
            <button onClick={() => setHeatmapModalOpen(false)} className="px-4 py-2 text-sm font-semibold bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300">Cancel</button>
            <button onClick={handleCreateHeatmap} className="px-4 py-2 text-sm font-semibold bg-primary text-white rounded-lg hover:bg-primary-dark">Create</button>
        </div>
      </Modal>

      {/* Delete Workbench Modal */}
      <DeleteWorkbenchModal
        isOpen={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        onConfirm={handleConfirmDelete}
        workbenchName={workbenchData?.workbench?.name || workbenchData?.name || 'Unknown'}
        isDeleting={isDeleting}
      />

      <div className="bg-white rounded-2xl shadow-sm flex-1 flex flex-col overflow-hidden min-h-0">
        {/* Scrollable content area */}
        <div
          ref={mainContentRef}
          className={`flex-1 min-h-0 p-4 ${activeTab === 'heatmap' ? 'overflow-y-auto scrollable-table' : 'overflow-y-auto'}`}
        >
            {renderContent()}
        </div>
      </div>
    </div>
  );
}


