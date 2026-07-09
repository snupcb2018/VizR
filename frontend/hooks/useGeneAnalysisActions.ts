import { useCallback, useState } from 'react';
import { apiService } from '../services/api';
import type { GOProvider } from '../components/GOProviderSubmenu';

interface UseGeneAnalysisActionsOptions {
  workbenchId: number;
  selectedGenes: string[];
  description: string;
  organism?: string;
  databases?: string[];
  pValueCutoff?: number;
}

export function useGeneAnalysisActions({
  workbenchId,
  selectedGenes,
  description,
  organism = 'arabidopsis',
  databases = ['GO_BP', 'GO_MF', 'GO_CC'],
  pValueCutoff = 0.05,
}: UseGeneAnalysisActionsOptions) {
  const [isGOModalOpen, setGOModalOpen] = useState(false);
  const [goAnalysisResult, setGOAnalysisResult] = useState<any>(null);
  const [isGOLoading, setGOLoading] = useState(false);
  const [isHeatmapModalOpen, setHeatmapModalOpen] = useState(false);
  const [isKEGGModalOpen, setKEGGModalOpen] = useState(false);

  const openHeatmap = useCallback(() => {
    setHeatmapModalOpen(true);
  }, []);

  const closeHeatmap = useCallback(() => {
    setHeatmapModalOpen(false);
  }, []);

  const openKEGG = useCallback(() => {
    setKEGGModalOpen(true);
  }, []);

  const closeKEGG = useCallback(() => {
    setKEGGModalOpen(false);
  }, []);

  const closeGOModal = useCallback(() => {
    setGOModalOpen(false);
  }, []);

  const runGOAnalysis = useCallback(
    async (provider: GOProvider) => {
      setGOLoading(true);
      setGOModalOpen(true);

      try {
        const result = await apiService.runGOEnrichment(workbenchId, {
          genes: selectedGenes,
          databases,
          p_value_cutoff: pValueCutoff,
          description,
          organism,
          provider,
        });
        setGOAnalysisResult(result);
      } catch (error) {
        console.error('[GO-ANALYSIS] Failed:', error);
      } finally {
        setGOLoading(false);
      }
    },
    [databases, description, organism, pValueCutoff, selectedGenes, workbenchId]
  );

  return {
    isGOModalOpen,
    goAnalysisResult,
    isGOLoading,
    closeGOModal,
    runGOAnalysis,
    isHeatmapModalOpen,
    openHeatmap,
    closeHeatmap,
    isKEGGModalOpen,
    openKEGG,
    closeKEGG,
  };
}
