import React, { useState, useEffect, useMemo } from 'react';
import Plot from 'react-plotly.js';

interface FragmentCountData {
  workbench_id: number;
  fragment_counts: Record<string, number>;
  groups: Record<string, string[]>;
  status: string;
}

interface WorkbenchDetailPCAReplicateFragmentCountProps {
  workbenchId: number;
  selectedGroup: string;
}

const WorkbenchDetailPCAReplicateFragmentCount: React.FC<WorkbenchDetailPCAReplicateFragmentCountProps> = ({
  workbenchId,
  selectedGroup
}) => {
  const [fragmentData, setFragmentData] = useState<FragmentCountData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await fetch(`/api/workbenches/${workbenchId}/pca/replicate-fragment-counts`);
        if (!response.ok) throw new Error('Failed to fetch fragment count data');
        const result = await response.json();

        if (result.status === 'not_available') {
          setError('Fragment count data not available');
          setIsLoading(false);
          return;
        }

        setFragmentData(result);
        setIsLoading(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error occurred');
        setIsLoading(false);
      }
    };

    fetchData();
  }, [workbenchId]);

  const plotData = useMemo(() => {
    if (!fragmentData || !selectedGroup) return [];

    const groupSamples = fragmentData.groups[selectedGroup] || [];
    const xValues = groupSamples;
    const yValues = groupSamples.map(sample => fragmentData.fragment_counts[sample] || 0);

    return [{
      x: xValues,
      y: yValues,
      type: 'bar',
      marker: {
        color: '#94a3b8',
        line: {
          width: 1,
          color: '#334155'
        }
      },
      hovertemplate: '<b>%{x}</b><br>Fragments: %{y:,.0f}<extra></extra>',
    }];
  }, [fragmentData, selectedGroup]);

  const statsData = useMemo(() => {
    if (!fragmentData || !selectedGroup) return null;

    const groupSamples = fragmentData.groups[selectedGroup] || [];
    const counts = groupSamples.map(sample => fragmentData.fragment_counts[sample] || 0);

    if (counts.length === 0) return null;

    const total = counts.reduce((a, b) => a + b, 0);
    const mean = total / counts.length;
    const min = Math.min(...counts);
    const max = Math.max(...counts);

    return { total, mean, min, max, count: counts.length };
  }, [fragmentData, selectedGroup]);

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

  if (!fragmentData) {
    return null;
  }

  return (
    <div className="space-y-4">
      {/* Stats Summary */}
      {statsData && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-gradient-to-br from-blue-50 to-blue-100 border border-blue-200 rounded-lg p-4">
            <div className="text-sm font-medium text-blue-700">Total Fragments</div>
            <div className="text-2xl font-bold text-blue-900 mt-1">
              {statsData.total.toLocaleString()}
            </div>
          </div>
          <div className="bg-gradient-to-br from-green-50 to-green-100 border border-green-200 rounded-lg p-4">
            <div className="text-sm font-medium text-green-700">Mean per Sample</div>
            <div className="text-2xl font-bold text-green-900 mt-1">
              {statsData.mean.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
          </div>
          <div className="bg-gradient-to-br from-purple-50 to-purple-100 border border-purple-200 rounded-lg p-4">
            <div className="text-sm font-medium text-purple-700">Min Fragments</div>
            <div className="text-2xl font-bold text-purple-900 mt-1">
              {statsData.min.toLocaleString()}
            </div>
          </div>
          <div className="bg-gradient-to-br from-pink-50 to-pink-100 border border-pink-200 rounded-lg p-4">
            <div className="text-sm font-medium text-pink-700">Max Fragments</div>
            <div className="text-2xl font-bold text-pink-900 mt-1">
              {statsData.max.toLocaleString()}
            </div>
          </div>
        </div>
      )}

      {/* Bar Chart */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Sum of Fragments for replicates of: {selectedGroup}
        </h3>
        <div className="flex justify-start">
          <Plot
            data={plotData as any}
            layout={{
              title: '',
              xaxis: {
                title: '',
              },
              yaxis: {
                title: 'Fragment Count',
                rangemode: 'tozero',
              },
              width: 700,
              height: 450,
              margin: {
                l: 80,
                r: 50,
                t: 20,
                b: 80,
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
        <h3 className="text-sm font-semibold text-blue-900 mb-2">Fragment Count Information</h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• Fragment counts represent the total number of sequenced reads per sample</li>
          <li>• Consistent fragment counts across replicates indicate good sequencing depth uniformity</li>
          <li>• Large variations may suggest technical issues or differences in library preparation</li>
        </ul>
      </div>
    </div>
  );
};

export default WorkbenchDetailPCAReplicateFragmentCount;
