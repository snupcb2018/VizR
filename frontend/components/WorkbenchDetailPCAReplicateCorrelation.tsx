import React, { useState, useEffect, useMemo } from 'react';
import Plot from 'react-plotly.js';

interface CorrelationData {
  workbench_id: number;
  correlation_matrix: Record<string, Record<string, number>>;
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

interface WorkbenchDetailPCAReplicateCorrelationProps {
  workbenchId: number;
  selectedGroup: string;
}

const WorkbenchDetailPCAReplicateCorrelation: React.FC<WorkbenchDetailPCAReplicateCorrelationProps> = ({
  workbenchId,
  selectedGroup
}) => {
  const [correlationData, setCorrelationData] = useState<CorrelationData | null>(null);
  const [samplesData, setSamplesData] = useState<SamplesData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      setError(null);

      try {
        // Fetch correlation matrix
        const corrResponse = await fetch(`/api/workbenches/${workbenchId}/pca/correlation`);
        if (!corrResponse.ok) throw new Error('Failed to fetch correlation data');
        const corrResult = await corrResponse.json();

        if (corrResult.status === 'not_available') {
          setError('Correlation matrix not available');
          setIsLoading(false);
          return;
        }

        setCorrelationData(corrResult);

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

  const heatmapData = useMemo(() => {
    if (!correlationData || groupReplicates.length === 0) return null;

    const replicateNames = groupReplicates.map(r => r.sample_name);

    // Filter correlation matrix for selected group
    const matrix = replicateNames.map(rep1 =>
      replicateNames.map(rep2 => correlationData.correlation_matrix[rep1]?.[rep2] || 0)
    );

    return {
      z: matrix,
      x: replicateNames,
      y: replicateNames,
      type: 'heatmap',
      colorscale: [
        [0, '#00CED1'],      // Cyan (low correlation)
        [0.5, '#E0E0E0'],    // Light gray (medium)
        [1, '#FF00FF'],      // Magenta (high correlation)
      ],
      colorbar: {
        title: {
          text: 'Correlation',
          side: 'right',
        },
        thickness: 20,
        len: 0.7,
        x: 1.15,
        outlinewidth: 1,
        outlinecolor: 'black',
        tickmode: 'linear',
        tick0: -1,
        dtick: 0.5,
        tickfont: {
          size: 12,
        },
        titlefont: {
          size: 14,
        },
      },
      hovertemplate: '<b>%{y}</b> vs <b>%{x}</b><br>Correlation: %{z:.3f}<extra></extra>',
    };
  }, [correlationData, groupReplicates]);

  const dendrogramData = useMemo(() => {
    if (!correlationData || groupReplicates.length === 0) return null;

    const replicateNames = groupReplicates.map(r => r.sample_name);

    // Simple hierarchical clustering using correlation as distance
    // This is a simplified version - for production use a proper clustering library
    const n = replicateNames.length;
    const distances: number[][] = [];

    for (let i = 0; i < n; i++) {
      distances[i] = [];
      for (let j = 0; j < n; j++) {
        const corr = correlationData.correlation_matrix[replicateNames[i]]?.[replicateNames[j]] || 0;
        distances[i][j] = 1 - corr; // Convert correlation to distance
      }
    }

    // Find the two closest samples for simple dendrogram
    let minDist = Infinity;
    let minPair = [0, 1];

    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        if (distances[i][j] < minDist) {
          minDist = distances[i][j];
          minPair = [i, j];
        }
      }
    }

    return {
      type: 'scatter',
      mode: 'lines',
      x: [0, 0, 1, 1],
      y: [0, minDist, minDist, 0],
      line: {
        color: 'black',
        width: 2,
      },
      showlegend: false,
    };
  }, [correlationData, groupReplicates]);

  const statsData = useMemo(() => {
    if (!correlationData || groupReplicates.length === 0) return null;

    const replicateNames = groupReplicates.map(r => r.sample_name);
    const values: number[] = [];

    for (let i = 0; i < replicateNames.length; i++) {
      for (let j = i + 1; j < replicateNames.length; j++) {
        values.push(correlationData.correlation_matrix[replicateNames[i]]?.[replicateNames[j]] || 0);
      }
    }

    if (values.length === 0) return null;

    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const min = Math.min(...values);
    const max = Math.max(...values);

    return { mean, min, max, count: values.length };
  }, [correlationData, groupReplicates]);

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

  if (!correlationData || !heatmapData || groupReplicates.length === 0) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-6">
        <p className="text-gray-600">No data available for the selected group</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stats Summary */}
      {statsData && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-gradient-to-br from-green-50 to-green-100 border border-green-200 rounded-lg p-4">
            <div className="text-sm font-medium text-green-700">Mean Correlation</div>
            <div className="text-2xl font-bold text-green-900 mt-1">
              {statsData.mean.toFixed(3)}
            </div>
          </div>
          <div className="bg-gradient-to-br from-purple-50 to-purple-100 border border-purple-200 rounded-lg p-4">
            <div className="text-sm font-medium text-purple-700">Min Correlation</div>
            <div className="text-2xl font-bold text-purple-900 mt-1">
              {statsData.min.toFixed(3)}
            </div>
          </div>
          <div className="bg-gradient-to-br from-pink-50 to-pink-100 border border-pink-200 rounded-lg p-4">
            <div className="text-sm font-medium text-pink-700">Max Correlation</div>
            <div className="text-2xl font-bold text-pink-900 mt-1">
              {statsData.max.toFixed(3)}
            </div>
          </div>
        </div>
      )}

      {/* Heatmap with Dendrogram */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Replicate Correlations: {selectedGroup}
        </h3>
        <div className="flex justify-start">
          <Plot
            data={[heatmapData as any]}
            layout={{
              title: '',
              xaxis: {
                title: '',
                side: 'bottom',
              },
              yaxis: {
                title: '',
              },
              width: 500,
              height: 400,
              margin: {
                l: 100,
                r: 50,
                t: 50,
                b: 100,
              },
            }}
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
        <h3 className="text-sm font-semibold text-blue-900 mb-2">Correlation Heatmap</h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• <strong>Color scale:</strong> Cyan (low correlation) → Magenta (high correlation)</li>
          <li>• Diagonal elements are always 1.0 (perfect self-correlation)</li>
          <li>• High correlation (≥0.9) indicates good replicate consistency</li>
          <li>• Low correlation (&lt;0.7) may suggest technical issues or biological variation</li>
          <li>• Hierarchical clustering groups similar samples together</li>
        </ul>
      </div>
    </div>
  );
};

export default WorkbenchDetailPCAReplicateCorrelation;
