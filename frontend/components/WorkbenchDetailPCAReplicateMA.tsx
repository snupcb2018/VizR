import React, { useState, useEffect, useMemo } from 'react';
import Plot from 'react-plotly.js';

interface ExpressionData {
  workbench_id: number;
  matrix: Record<string, Record<string, number>>;
  genes: string[];
  samples: string[];
  status: string;
}

interface SampleInfo {
  sample_name: string;
  condition: string;
}

interface SamplesData {
  workbench_id: number;
  samples: SampleInfo[];
  groups: string[];
  status: string;
}

interface WorkbenchDetailPCAReplicateMAProps {
  workbenchId: number;
  selectedGroup: string;
}

const WorkbenchDetailPCAReplicateMA: React.FC<WorkbenchDetailPCAReplicateMAProps> = ({
  workbenchId,
  selectedGroup
}) => {
  const [expressionData, setExpressionData] = useState<ExpressionData | null>(null);
  const [samplesData, setSamplesData] = useState<SamplesData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      setError(null);

      try {
        // Fetch expression matrix (limit to 1000 genes for MA plot)
        const expressionResponse = await fetch(
          `/api/workbenches/${workbenchId}/pca/expression-matrix?page=1&page_size=1000`
        );
        if (!expressionResponse.ok) throw new Error('Failed to fetch expression data');
        const expressionResult = await expressionResponse.json();

        if (expressionResult.status === 'not_available') {
          setError('Expression data not available');
          setIsLoading(false);
          return;
        }

        setExpressionData(expressionResult);

        // Fetch sample information
        const samplesResponse = await fetch(`/api/workbenches/${workbenchId}/pca/samples`);
        if (!samplesResponse.ok) throw new Error('Failed to fetch sample information');
        const samplesResult = await samplesResponse.json();

        if (samplesResult.status === 'not_available') {
          setError('Sample information not available');
          setIsLoading(false);
          return;
        }

        setSamplesData(samplesResult);
        setIsLoading(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error occurred');
        setIsLoading(false);
      }
    };

    fetchData();
  }, [workbenchId]);

  const groupReplicates = useMemo(() => {
    if (!samplesData || !selectedGroup) return [];
    return samplesData.samples.filter(s => s.condition === selectedGroup);
  }, [samplesData, selectedGroup]);

  const maPlotData = useMemo(() => {
    if (!expressionData || groupReplicates.length === 0) return [];

    const replicates = groupReplicates.map(r => r.sample_name);
    const n = replicates.length;

    // Create MA plot matrix data
    const plotData = [];

    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        if (i === j) continue; // Skip diagonal

        const sample1 = replicates[j];
        const sample2 = replicates[i];

        // Calculate M (log ratio) and A (average intensity)
        const aValues = [];
        const mValues = [];

        for (const gene of expressionData.genes) {
          const val1 = expressionData.matrix[gene]?.[sample1] || 0;
          const val2 = expressionData.matrix[gene]?.[sample2] || 0;

          // A = average of log2 values
          const a = (val1 + val2) / 2;

          // M = difference of log2 values (log2 fold change)
          const m = val1 - val2;

          // Filter out invalid values
          if (isFinite(a) && isFinite(m)) {
            aValues.push(a);
            mValues.push(m);
          }
        }

        // Use consistent indexing: row * n + col
        const subplotIdx = i * n + j;
        const xaxisRef = subplotIdx === 0 ? 'x' : `x${subplotIdx + 1}`;
        const yaxisRef = subplotIdx === 0 ? 'y' : `y${subplotIdx + 1}`;

        plotData.push({
          x: aValues,
          y: mValues,
          type: 'scattergl',
          mode: 'markers',
          marker: {
            size: 2,
            color: 'black',
            opacity: 0.5,
          },
          xaxis: xaxisRef,
          yaxis: yaxisRef,
          showlegend: false,
          hoverinfo: 'skip',
        });
      }
    }

    return plotData;
  }, [expressionData, groupReplicates]);

  const layout = useMemo(() => {
    if (groupReplicates.length === 0 || !expressionData) return {};

    const replicates = groupReplicates.map(r => r.sample_name);
    const n = replicates.length;

    // Calculate symmetric ranges for A and M
    const allAValues: number[] = [];
    const allMValues: number[] = [];

    for (const gene of expressionData.genes) {
      for (let i = 0; i < replicates.length; i++) {
        for (let j = 0; j < replicates.length; j++) {
          if (i === j) continue;

          const val1 = expressionData.matrix[gene]?.[replicates[j]] || 0;
          const val2 = expressionData.matrix[gene]?.[replicates[i]] || 0;

          const a = (val1 + val2) / 2;
          const m = val1 - val2;

          if (isFinite(a)) allAValues.push(Math.abs(a));
          if (isFinite(m)) allMValues.push(Math.abs(m));
        }
      }
    }

    const maxAbsA = Math.max(...allAValues);
    const maxAbsM = Math.max(...allMValues);
    const symmetricRangeA: [number, number] = [-maxAbsA, maxAbsA];
    const symmetricRangeM: [number, number] = [-maxAbsM, maxAbsM];

    const spacing = 0.02; // Space between subplots
    const plotWidth = (1.0 - (n - 1) * spacing) / n;
    const plotHeight = (1.0 - (n - 1) * spacing) / n;

    // Calculate adaptive font size based on sample name length and subplot width
    const plotAreaWidth = 500 - 60 - 60;
    const subplotPixelWidth = plotAreaWidth * plotWidth;
    const maxNameLength = Math.max(...replicates.map(r => r.length));
    const fontSize = Math.min(16, Math.max(8, Math.floor(subplotPixelWidth / (maxNameLength * 0.65))));

    const layoutConfig: any = {
      title: `Replicate MA: ${selectedGroup}`,
      width: 500,
      height: 500,
      margin: {
        l: 60,
        r: 60,
        t: 80,
        b: 60,
      },
      annotations: [],
    };

    // Configure axes with manual domain positioning
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        // Use consistent indexing: row * n + col (same as trace data)
        const subplotIdx = i * n + j;
        const xKey = subplotIdx === 0 ? 'xaxis' : `xaxis${subplotIdx + 1}`;
        const yKey = subplotIdx === 0 ? 'yaxis' : `yaxis${subplotIdx + 1}`;

        // Calculate domain for this subplot
        const xDomain = [
          j * (plotWidth + spacing),
          j * (plotWidth + spacing) + plotWidth
        ];
        const yTop = 1 - i * (plotHeight + spacing);
        const yBottom = yTop - plotHeight;
        const yDomain = [yBottom, yTop];

        layoutConfig[xKey] = {
          domain: xDomain,
          title: i === n - 1 ? replicates[j] : '',
          showticklabels: i === n - 1,
          anchor: yKey.replace('yaxis', 'y'),
          showline: true,
          linewidth: 1,
          linecolor: 'black',
          mirror: true,
          range: symmetricRangeA,
        };

        layoutConfig[yKey] = {
          domain: yDomain,
          title: j === 0 ? replicates[i] : '',
          showticklabels: j === 0,
          zeroline: true,
          zerolinewidth: 1,
          zerolinecolor: '#cccccc',
          anchor: xKey.replace('xaxis', 'x'),
          showline: true,
          linewidth: 1,
          linecolor: 'black',
          mirror: true,
          range: symmetricRangeM,
        };

        // Add replicate name annotation for diagonal positions
        if (i === j) {
          const xCenter = (xDomain[0] + xDomain[1]) / 2;
          const yCenter = (yDomain[0] + yDomain[1]) / 2;

          layoutConfig.annotations.push({
            text: replicates[i],
            xref: 'paper',
            yref: 'paper',
            x: xCenter,
            y: yCenter,
            xanchor: 'center',
            yanchor: 'middle',
            showarrow: false,
            font: {
              size: fontSize,
              color: 'black',
              family: 'Arial, sans-serif',
            },
          });
        }
      }
    }

    return layoutConfig;
  }, [groupReplicates, selectedGroup]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
        <div className="flex items-center">
          <svg className="w-6 h-6 text-yellow-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <h3 className="text-yellow-800 font-semibold">Data Not Available</h3>
            <p className="text-yellow-700 text-sm mt-1">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!expressionData || groupReplicates.length === 0) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-6">
        <p className="text-gray-600">No data available for the selected group</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* MA Plot Matrix */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Replicate MA: {selectedGroup}
        </h3>
        <div className="flex justify-start">
          <Plot
            data={maPlotData as any}
            layout={layout}
            config={{
              responsive: true,
              displayModeBar: true,
              displaylogo: false,
              modeBarButtonsToRemove: ['lasso2d', 'select2d'],
            }}
          />
        </div>
      </div>

      {/* Info Panel */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-blue-900 mb-2">MA Plot Matrix</h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• <strong>M (Y-axis):</strong> Log2 fold change between replicates (difference)</li>
          <li>• <strong>A (X-axis):</strong> Average log2 expression intensity</li>
          <li>• Points centered around M=0 indicate consistent expression between replicates</li>
          <li>• Deviation from M=0 suggests differential expression or technical variation</li>
          <li>• Red points indicate genes with larger fold changes</li>
        </ul>
      </div>
    </div>
  );
};

export default WorkbenchDetailPCAReplicateMA;
