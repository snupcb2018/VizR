import React, { useState, useEffect, useMemo } from 'react';
import { WgcnaParams, WgcnaModuleData } from '../types';
import { apiService } from '../services/api';
import WgcnaModuleGeneTable from './WgcnaModuleGeneTable';
import { VennSetSummary } from './VennSetMenu';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';

interface WgcnaModuleDetailProps {
  workbenchId: number;
  moduleId: string;
  params: WgcnaParams;
  selectedGenes: Set<string>;
  onSelectionChange: (genes: Set<string>) => void;
  onNavigateToVennDiagram: (genes: string[], targetSetIndex?: number) => void;
  vennSetSummaries?: VennSetSummary[];
}

export function WgcnaModuleDetail({
  workbenchId,
  moduleId,
  params,
  selectedGenes,
  onSelectionChange,
  onNavigateToVennDiagram,
  vennSetSummaries
}: WgcnaModuleDetailProps) {
  const [data, setData] = useState<WgcnaModuleData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showGenes, setShowGenes] = useState(false);

  // Maximum number of genes to display on chart for performance
  const MAX_DISPLAY_GENES = 100;

  useEffect(() => {
    // Module change - reset selection
    onSelectionChange(new Set());
    loadModuleData();
  }, [moduleId, params]);

  const loadModuleData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiService.getWgcnaModuleData(workbenchId, moduleId, {
        source_type: params.sourceType,
        p_value: params.sourceType === 'deg' ? params.pValue : undefined,
        fold_change: params.sourceType === 'deg' ? params.foldChange : undefined,
        top_n_genes: params.sourceType === 'variance' ? params.topNGenes : undefined,
        soft_power: params.softPower,
        min_module_size: params.minModuleSize,
        deep_split: params.deepSplit,
        merge_cut_height: params.mergeCutHeight
      });
      setData(response);
    } catch (error: any) {
      console.error('Failed to load module data:', error);
      setError(error.message || 'Failed to load module data');
    } finally {
      setIsLoading(false);
    }
  };

  // Select top genes for display based on module membership (kME)
  const topGenes = useMemo(() => {
    if (!data || !data.genes || data.genes.length === 0) return [];

    // Sort by module_membership (kME) descending and take top N
    const sorted = [...data.genes].sort((a, b) => b.module_membership - a.module_membership);
    return sorted.slice(0, Math.min(MAX_DISPLAY_GENES, sorted.length));
  }, [data]);

  // Prepare chart data with eigengene and individual genes
  const chartData = useMemo(() => {
    if (!data) return [];

    const chartPoints = data.samples.map((sample, idx) => ({
      sample,
      eigengene: data.eigengene_values ? data.eigengene_values[idx] : 0
    }));

    // Add individual gene data if showing genes
    topGenes.forEach((gene, geneIdx) => {
      data.samples.forEach((sample, sampleIdx) => {
        const value = gene[sample];
        const numValue = typeof value === 'number' ? value : parseFloat(value as string) || 0;
        chartPoints[sampleIdx][`gene_${geneIdx}`] = numValue;
      });
    });

    return chartPoints;
  }, [data, topGenes]);

  // WGCNA module color mapping
  const moduleColorMap: Record<string, string> = {
    turquoise: '#40E0D0',
    blue: '#4169E1',
    brown: '#8B4513',
    yellow: '#FFD700',
    green: '#32CD32',
    red: '#DC143C',
    black: '#000000',
    pink: '#FF69B4',
    magenta: '#FF00FF',
    purple: '#9370DB',
    greenyellow: '#ADFF2F',
    tan: '#D2B48C',
    salmon: '#FA8072',
    cyan: '#00FFFF',
    midnightblue: '#191970',
    lightcyan: '#E0FFFF',
    grey: '#808080',
    gray: '#808080'
  };

  const moduleColor = moduleColorMap[moduleId.toLowerCase()] || '#808080';

  return (
    <div className="space-y-4 relative">
      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center z-10 rounded-lg">
          <div className="flex flex-col items-center gap-2">
            <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
            <p className="text-sm text-gray-600">Loading module data...</p>
          </div>
        </div>
      )}

      {/* Error message */}
      {error && !isLoading && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* Content */}
      {data && (
        <>
          {/* Eigengene Pattern Chart */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
            <div className="p-4 border-b border-gray-200">
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-3">
                    <div
                      className="w-6 h-6 rounded border-2 border-white shadow-sm"
                      style={{ backgroundColor: moduleColor }}
                    />
                    <h3 className="text-lg font-semibold text-gray-800">
                      Module Eigengene Pattern: {moduleId.charAt(0).toUpperCase() + moduleId.slice(1)}
                    </h3>
                  </div>
                  <p className="text-sm text-gray-600 mt-1">
                    {data.gene_count.toLocaleString()} genes · WGCNA co-expression module
                    {showGenes && data.gene_count > MAX_DISPLAY_GENES && (
                      <span className="ml-2 text-blue-600">
                        (showing top {MAX_DISPLAY_GENES} genes by kME)
                      </span>
                    )}
                  </p>
                  <div className="text-xs text-gray-500 mt-2 space-x-3">
                    <span>Source: {params.sourceType}</span>
                    {params.sourceType === 'deg' && (
                      <>
                        <span>P-value: {params.pValue}</span>
                        <span>Log2 FC: {params.foldChange}</span>
                      </>
                    )}
                    {params.sourceType === 'variance' && (
                      <span>Top genes: {params.topNGenes}</span>
                    )}
                    <span>Soft power: {params.softPower}</span>
                    <span>Min module size: {params.minModuleSize}</span>
                  </div>
                </div>

                {/* Toggle for individual genes */}
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={showGenes}
                    onChange={(e) => setShowGenes(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="relative w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-gray-600"></div>
                  <span className="text-sm text-gray-700">Show Genes</span>
                </label>
              </div>
            </div>

            {/* Chart */}
            <div className="p-4">
              <ResponsiveContainer width="100%" height={400}>
                <LineChart
                  data={chartData}
                  margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                  <XAxis
                    dataKey="sample"
                    tick={{ fontSize: 12 }}
                    angle={-45}
                    textAnchor="end"
                    height={80}
                  />
                  <YAxis
                    label={{ value: 'Expression Value', angle: -90, position: 'insideLeft', style: { fontSize: 12 } }}
                    tick={{ fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'rgba(255, 255, 255, 0.95)',
                      border: '1px solid #ccc',
                      borderRadius: '4px',
                      fontSize: '12px'
                    }}
                    formatter={(value: any) => [typeof value === 'number' ? value.toFixed(3) : value]}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px' }} iconType="line" />

                  {/* Individual gene patterns (gray, semi-transparent) */}
                  {showGenes && topGenes.map((_, geneIdx) => (
                    <Line
                      key={`gene_${geneIdx}`}
                      type="monotone"
                      dataKey={`gene_${geneIdx}`}
                      stroke="rgba(120, 120, 120, 0.35)"
                      strokeWidth={0.8}
                      dot={false}
                      legendType="none"
                      isAnimationActive={false}
                    />
                  ))}

                  {/* Module Eigengene (bold) */}
                  <Line
                    type="monotone"
                    dataKey="eigengene"
                    stroke={moduleColor}
                    strokeWidth={3}
                    dot={{ fill: moduleColor, r: 3 }}
                    activeDot={{ r: 5 }}
                    name="Module Eigengene"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Gene Table */}
          <WgcnaModuleGeneTable
            genes={data.genes}
            samples={data.samples}
            moduleId={moduleId}
            workbenchId={workbenchId}
            selectedGenes={selectedGenes}
            onSelectionChange={onSelectionChange}
            params={params}
            onNavigateToVennDiagram={onNavigateToVennDiagram}
            vennSetSummaries={vennSetSummaries}
          />
        </>
      )}
    </div>
  );
}
