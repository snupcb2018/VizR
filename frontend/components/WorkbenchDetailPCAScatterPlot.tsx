import React, { useState, useEffect, useMemo } from 'react';
import Plot from 'react-plotly.js';

interface PCAData {
  workbench_id: number;
  pca_scores: Record<string, Record<string, number>>;
  samples: string[];
  components: string[];
  num_components: number;
  variance_explained: Record<string, number> | null;
  status: string;
}

interface SampleInfo {
  sample_name: string;
  condition: string;
  replicate: number;
  file_paths: string[];
}

interface SamplesData {
  workbench_id: number;
  samples: SampleInfo[];
  groups: string[];
  layout: string;
  status: string;
}

interface WorkbenchDetailPCAScatterPlotProps {
  workbenchId: number;
}

const WorkbenchDetailPCAScatterPlot: React.FC<WorkbenchDetailPCAScatterPlotProps> = ({ workbenchId }) => {
  const [pcaData, setPcaData] = useState<PCAData | null>(null);
  const [samplesData, setSamplesData] = useState<SamplesData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPCX, setSelectedPCX] = useState<string>('PC1');
  const [selectedPCY, setSelectedPCY] = useState<string>('PC2');

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      setError(null);

      try {
        // Fetch PCA scores data
        const pcaResponse = await fetch(`/api/workbenches/${workbenchId}/pca/data`);
        if (!pcaResponse.ok) throw new Error('Failed to fetch PCA data');
        const pcaResult = await pcaResponse.json();

        if (pcaResult.status === 'not_available') {
          setError('PCA analysis not yet performed. Please run the analysis first.');
          setIsLoading(false);
          return;
        }

        setPcaData(pcaResult);

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

  const axisRanges = useMemo(() => {
    if (!pcaData || !samplesData) return null;

    const allX = samplesData.samples.map(s => pcaData.pca_scores[s.sample_name]?.[selectedPCX]).filter(v => v != null) as number[];
    const allY = samplesData.samples.map(s => pcaData.pca_scores[s.sample_name]?.[selectedPCY]).filter(v => v != null) as number[];

    if (allX.length === 0 || allY.length === 0) return null;

    const xPad = (Math.max(...allX) - Math.min(...allX)) * 0.1;
    const yPad = (Math.max(...allY) - Math.min(...allY)) * 0.1;

    return {
      x: [Math.min(...allX) - xPad, Math.max(...allX) + xPad],
      y: [Math.min(...allY) - yPad, Math.max(...allY) + yPad],
    };
  }, [pcaData, samplesData, selectedPCX, selectedPCY]);

  const orderedGroups = useMemo(() => {
    if (!samplesData) return [];

    // Preserve Step 2 mapping order from vizr_pipeline_samples JSON
    const seen = new Set<string>();
    const ordered: string[] = [];
    samplesData.samples.forEach((sample) => {
      const group = sample.condition;
      if (group && !seen.has(group)) {
        seen.add(group);
        ordered.push(group);
      }
    });

    return ordered.length > 0 ? ordered : samplesData.groups;
  }, [samplesData]);

  const plotData = useMemo(() => {
    if (!pcaData || !samplesData) {
      return [];
    }

    // Distinguish groups by open marker shape and per-group color.
    const symbolPalette = [
      'circle-open', 'square-open', 'triangle-up-open', 'x-thin-open', 'diamond-open', 'cross-open',
      'triangle-down-open', 'star-open', 'pentagon-open', 'hexagon-open', 'triangle-right-open', 'triangle-left-open'
    ];
    const colorPalette = [
      '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b',
      '#e377c2', '#7f7f7f', '#bcbd22', '#17becf', '#ff1493', '#00ced1'
    ];
    const groupColors: Record<string, string> = {};
    const groupSymbols: Record<string, string> = {};
    const colorCount = colorPalette.length;
    const symbolCount = symbolPalette.length;
    orderedGroups.forEach((group, index) => {
      // Priority: use all symbols first, then rotate color for the next symbol cycle.
      const symbolIndex = index % symbolCount;
      const colorIndex = Math.floor(index / symbolCount) % colorCount;
      groupColors[group] = colorPalette[colorIndex];
      groupSymbols[group] = symbolPalette[symbolIndex];
    });

    const traces = orderedGroups.map((group) => {
      const groupSamples = samplesData.samples.filter(s => s.condition === group);

      const x = groupSamples.map(s => {
        const scoreData = pcaData.pca_scores[s.sample_name];
        return scoreData ? scoreData[selectedPCX] : null;
      });
      const y = groupSamples.map(s => pcaData.pca_scores[s.sample_name]?.[selectedPCY]);
      const text = groupSamples.map(s => s.sample_name);

      return {
        x,
        y,
        mode: 'markers',
        type: 'scatter',
        name: group,
        text,
        marker: {
          size: 12,
          symbol: groupSymbols[group],
          color: groupColors[group],
          line: {
            width: 2,
            color: groupColors[group],
          },
        },
        hovertemplate: '<b>%{text}</b><br>' +
          `${selectedPCX}: %{x:.3f}<br>` +
          `${selectedPCY}: %{y:.3f}<br>` +
          '<extra></extra>',
      };
    });

    return traces;
  }, [pcaData, samplesData, orderedGroups, selectedPCX, selectedPCY]);

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

  if (!pcaData || !samplesData) {
    return null;
  }

  const getAxisLabel = (pc: string): string => {
    if (pcaData.variance_explained && pcaData.variance_explained[pc]) {
      const variance = pcaData.variance_explained[pc].toFixed(2);
      return `${pc} (${variance}%)`;
    }
    return pc;
  };

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex items-center gap-4 bg-gray-50 p-4 rounded-lg">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">X-axis:</label>
          <select
            value={selectedPCX}
            onChange={(e) => setSelectedPCX(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {pcaData.components.map((pc) => (
              <option key={pc} value={pc}>{getAxisLabel(pc)}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">Y-axis:</label>
          <select
            value={selectedPCY}
            onChange={(e) => setSelectedPCY(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {pcaData.components.map((pc) => (
              <option key={pc} value={pc}>{getAxisLabel(pc)}</option>
            ))}
          </select>
        </div>
        <div className="ml-auto text-sm text-gray-600">
          {pcaData.samples.length} samples, {pcaData.num_components} components
        </div>
      </div>

      {/* PCA Plot */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 flex justify-center">
        <Plot
          data={plotData as any}
          layout={{
            title: {
              text: `PCA: ${getAxisLabel(selectedPCX)} vs ${getAxisLabel(selectedPCY)}`,
            },
            xaxis: {
              title: {
                text: getAxisLabel(selectedPCX),
              },
              zeroline: true,
              zerolinewidth: 1,
              zerolinecolor: '#cccccc',
              ...(axisRanges ? { autorange: false, range: axisRanges.x } : {}),
            },
            yaxis: {
              title: {
                text: getAxisLabel(selectedPCY),
              },
              zeroline: true,
              zerolinewidth: 1,
              zerolinecolor: '#cccccc',
              ...(axisRanges ? { autorange: false, range: axisRanges.y } : {}),
            },
            hovermode: 'closest',
            showlegend: true,
            legend: {
              x: 1.02,
              y: 1,
              xanchor: 'left',
              yanchor: 'top',
            },
            width: 600,
            height: 600,
          }}
          config={{
            responsive: true,
            displayModeBar: true,
            displaylogo: false,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'],
            doubleClickDelay: 600,
          }}
        />
      </div>

      {/* Sample Groups Info */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Sample Groups</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {orderedGroups.map((group) => {
            const groupSamples = samplesData.samples.filter(s => s.condition === group);
            return (
              <div key={group} className="bg-white p-3 rounded border border-gray-200">
                <div className="font-medium text-gray-900 mb-1">{group}</div>
                <div className="text-sm text-gray-600">
                  {groupSamples.length} samples
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {groupSamples.map(s => s.sample_name).join(', ')}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default WorkbenchDetailPCAScatterPlot;
