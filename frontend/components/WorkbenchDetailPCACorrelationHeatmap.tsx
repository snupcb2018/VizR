import React, { useState, useEffect, useMemo } from 'react';
import Plot from 'react-plotly.js';

interface ClusteredCorrelationData {
  workbench_id: number;
  correlation_matrix: Record<string, Record<string, number>>;
  samples: string[];
  row_dendrogram: {
    icoord: number[][];
    dcoord: number[][];
    leaves: number[];
    color_list: string[];
  };
  col_dendrogram: {
    icoord: number[][];
    dcoord: number[][];
    leaves: number[];
    color_list: string[];
  };
  sample_groups: Record<string, string>;
  group_colors: Record<string, string>;
  status: string;
}

interface WorkbenchDetailPCACorrelationHeatmapProps {
  workbenchId: number;
}

const WorkbenchDetailPCACorrelationHeatmap: React.FC<WorkbenchDetailPCACorrelationHeatmapProps> = ({ workbenchId }) => {
  const [correlationData, setCorrelationData] = useState<ClusteredCorrelationData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      setError(null);

      try {
        // Fetch clustered correlation matrix
        const corrResponse = await fetch(`/api/workbenches/${workbenchId}/pca/correlation-clustered`);
        if (!corrResponse.ok) throw new Error('Failed to fetch correlation data');
        const corrResult = await corrResponse.json();

        if (corrResult.status === 'not_available') {
          setError('Correlation matrix not available. Please run PCA analysis first.');
          setIsLoading(false);
          return;
        }

        setCorrelationData(corrResult);
        setIsLoading(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error occurred');
        setIsLoading(false);
      }
    };

    fetchData();
  }, [workbenchId]);

  const plotData = useMemo(() => {
    if (!correlationData) return null;

    const samples = correlationData.samples;
    const n = samples.length;

    const matrix = samples.map(sample1 =>
      samples.map(sample2 => correlationData.correlation_matrix[sample1][sample2])
    );

    const rowDend = correlationData.row_dendrogram;
    const colDend = correlationData.col_dendrogram;

    // Calculate dynamic dimensions based on sample count and name length
    const maxSampleNameLength = Math.max(...samples.map(s => s.length));

    // Font size assumption: ~7 pixels per character on average
    const charWidth = 7;
    const charHeight = 12;

    // Calculate margins based on rotated text (-45 degrees)
    // For 45-degree rotation: diagonal = length * sqrt(2) / 2
    const maxNameWidth = maxSampleNameLength * charWidth;
    const rotatedHeight = maxNameWidth * 0.707; // sin(45°) ≈ 0.707

    // Dynamic margins
    const bottomMargin = Math.max(150, rotatedHeight + 50);
    const rightMargin = Math.max(150, rotatedHeight + 50);

    // Dynamic plot dimensions: min 500, grows with sample count
    const plotWidth = Math.max(600, 400 + n * 15);
    const plotHeight = Math.max(600, 400 + n * 15);

    // Calculate colorbar position based on longest sample name
    const colorbarX = 1.08 + (maxSampleNameLength * 0.005) + 0.08; // base + char_factor + margin

    // Helper function to convert scipy dendrogram coordinates to sample indices
    // scipy uses: (index * 10) + 5, so we reverse: (coord - 5) / 10
    const convertDendCoord = (coord: number) => (coord - 5) / 10;

    // Top dendrogram (column clustering) - positioned above heatmap
    const topDendrogramX: number[] = [];
    const topDendrogramY: number[] = [];

    colDend.icoord.forEach((icoord) => {
      const dcoord = colDend.dcoord[colDend.icoord.indexOf(icoord)];
      for (let i = 0; i < icoord.length; i++) {
        topDendrogramX.push(convertDendCoord(icoord[i]));
        topDendrogramY.push(dcoord[i]);
      }
      topDendrogramX.push(null as any);
      topDendrogramY.push(null as any);
    });

    // Left dendrogram (row clustering) - positioned left of heatmap
    const leftDendrogramX: number[] = [];
    const leftDendrogramY: number[] = [];

    rowDend.icoord.forEach((icoord) => {
      const dcoord = rowDend.dcoord[rowDend.icoord.indexOf(icoord)];
      for (let i = 0; i < icoord.length; i++) {
        // For left dendrogram, swap x and y, and reverse y axis
        leftDendrogramX.push(dcoord[i]);
        leftDendrogramY.push(convertDendCoord(icoord[i]));
      }
      leftDendrogramX.push(null as any);
      leftDendrogramY.push(null as any);
    });

    // Main heatmap
    const heatmapTrace = {
      type: 'heatmap',
      z: matrix,
      x: samples.map((_, i) => i),
      y: samples.map((_, i) => i),
      xaxis: 'x',
      yaxis: 'y',
      colorscale: [
        [0, '#7B3F99'],    // Purple for low correlation
        [0.5, '#FFFFFF'],  // White for medium
        [1, '#FFD700']     // Yellow/Gold for high correlation
      ],
      colorbar: {
        title: { text: 'Value', side: 'right' },
        thickness: 15,
        len: 0.7,
        x: colorbarX,
        y: 0.4,
      },
      hovertemplate: '<b>%{y}</b> vs <b>%{x}</b><br>Correlation: %{z:.3f}<extra></extra>',
      showscale: true,
    };

    // Top dendrogram trace
    const topDendrogramTrace = {
      type: 'scatter',
      mode: 'lines',
      x: topDendrogramX,
      y: topDendrogramY,
      xaxis: 'x2',
      yaxis: 'y2',
      line: { color: 'black', width: 1 },
      hoverinfo: 'none',
      showlegend: false,
    };

    // Left dendrogram trace
    const leftDendrogramTrace = {
      type: 'scatter',
      mode: 'lines',
      x: leftDendrogramX,
      y: leftDendrogramY,
      xaxis: 'x3',
      yaxis: 'y3',
      line: { color: 'black', width: 1 },
      hoverinfo: 'none',
      showlegend: false,
    };

    // Create shapes for sample group color bars
    const topColorBarShapes = samples.map((sample, idx) => {
      const group = correlationData.sample_groups[sample];
      const color = correlationData.group_colors[group] || '#CCCCCC';
      return {
        type: 'rect',
        xref: 'x',
        yref: 'paper',
        x0: idx - 0.5,
        x1: idx + 0.5,
        y0: 0.77,
        y1: 0.785,
        fillcolor: color,
        line: { width: 0 },
      };
    });

    const leftColorBarShapes = samples.map((sample, idx) => {
      const group = correlationData.sample_groups[sample];
      const color = correlationData.group_colors[group] || '#CCCCCC';
      return {
        type: 'rect',
        xref: 'paper',
        yref: 'y',
        x0: 0.13,
        x1: 0.15,
        y0: idx - 0.5,
        y1: idx + 0.5,
        fillcolor: color,
        line: { width: 0 },
      };
    });

    return {
      heatmapTrace,
      topDendrogramTrace,
      leftDendrogramTrace,
      samples,
      n,
      topColorBarShapes,
      leftColorBarShapes,
      plotWidth,
      plotHeight,
      bottomMargin,
      rightMargin,
    };
  }, [correlationData]);

  const calculateStats = useMemo(() => {
    if (!correlationData) return null;

    const values: number[] = [];
    const samples = correlationData.samples;

    for (let i = 0; i < samples.length; i++) {
      for (let j = i + 1; j < samples.length; j++) {
        values.push(correlationData.correlation_matrix[samples[i]][samples[j]]);
      }
    }

    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const min = Math.min(...values);
    const max = Math.max(...values);

    return { mean, min, max, count: values.length };
  }, [correlationData]);

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

  if (!correlationData || !plotData) {
    return null;
  }

  const tickvals = Array.from({ length: plotData.n }, (_, i) => i);
  const ticktext = plotData.samples;

  return (
    <div className="space-y-4">
      {/* Stats Summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gradient-to-br from-blue-50 to-blue-100 border border-blue-200 rounded-lg p-4">
          <div className="text-sm font-medium text-blue-700">Total Samples</div>
          <div className="text-2xl font-bold text-blue-900 mt-1">
            {correlationData.samples.length}
          </div>
        </div>
        <div className="bg-gradient-to-br from-green-50 to-green-100 border border-green-200 rounded-lg p-4">
          <div className="text-sm font-medium text-green-700">Mean Correlation</div>
          <div className="text-2xl font-bold text-green-900 mt-1">
            {calculateStats?.mean.toFixed(3)}
          </div>
        </div>
        <div className="bg-gradient-to-br from-purple-50 to-purple-100 border border-purple-200 rounded-lg p-4">
          <div className="text-sm font-medium text-purple-700">Min Correlation</div>
          <div className="text-2xl font-bold text-purple-900 mt-1">
            {calculateStats?.min.toFixed(3)}
          </div>
        </div>
        <div className="bg-gradient-to-br from-pink-50 to-pink-100 border border-pink-200 rounded-lg p-4">
          <div className="text-sm font-medium text-pink-700">Max Correlation</div>
          <div className="text-2xl font-bold text-pink-900 mt-1">
            {calculateStats?.max.toFixed(3)}
          </div>
        </div>
      </div>

      {/* Heatmap with Dendrograms */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Sample Correlation Matrix
        </h3>
        <div className="flex justify-start">
          <Plot
            data={[
              plotData.heatmapTrace as any,
              plotData.topDendrogramTrace as any,
              plotData.leftDendrogramTrace as any,
            ]}
            layout={{
              title: '',
              // Main heatmap axes
              xaxis: {
                domain: [0.20, 0.95],
                anchor: 'y',
                side: 'bottom',
                tickmode: 'array',
                tickvals: tickvals,
                ticktext: ticktext,
                tickangle: -45,
                showgrid: false,
                zeroline: false,
                range: [-0.5, plotData.n - 0.5],
              },
              yaxis: {
                domain: [0, 0.75],
                anchor: 'x',
                side: 'right',
                tickmode: 'array',
                tickvals: tickvals,
                ticktext: ticktext,
                showgrid: false,
                zeroline: false,
                range: [-0.5, plotData.n - 0.5],
              },
              // Top dendrogram axes
              xaxis2: {
                domain: [0.20, 0.95],
                anchor: 'y2',
                showticklabels: false,
                showgrid: false,
                zeroline: false,
                range: [-0.5, plotData.n - 0.5],
              },
              yaxis2: {
                domain: [0.8, 1],
                anchor: 'x2',
                showticklabels: false,
                showgrid: false,
                zeroline: false,
              },
              // Left dendrogram axes
              xaxis3: {
                domain: [0, 0.1],
                anchor: 'y3',
                showticklabels: false,
                showgrid: false,
                zeroline: false,
                autorange: 'reversed',
              },
              yaxis3: {
                domain: [0, 0.75],
                anchor: 'x3',
                showticklabels: false,
                showgrid: false,
                zeroline: false,
                range: [-0.5, plotData.n - 0.5],
              },
              width: plotData.plotWidth,
              height: plotData.plotHeight,
              margin: {
                l: 150,
                r: plotData.rightMargin,
                t: 30,
                b: plotData.bottomMargin,
              },
              paper_bgcolor: 'white',
              plot_bgcolor: 'white',
              shapes: [
                ...plotData.topColorBarShapes,
                ...plotData.leftColorBarShapes,
              ],
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

      {/* Sample Groups Legend */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Sample Groups</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Object.entries(correlationData.group_colors).map(([group, color]) => {
            const groupSamples = correlationData.samples.filter(
              s => correlationData.sample_groups[s] === group
            );
            return (
              <div key={group} className="bg-white p-3 rounded border border-gray-200">
                <div className="flex items-center gap-2 mb-1">
                  <div
                    className="w-4 h-4 rounded"
                    style={{ backgroundColor: color }}
                  />
                  <div className="font-medium text-gray-900">{group}</div>
                </div>
                <div className="text-xs text-gray-500">
                  {groupSamples.join(', ')}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Interpretation Guide */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-blue-900 mb-2">Interpretation Guide</h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• <strong>High correlation (≥0.9):</strong> Samples are very similar in expression patterns</li>
          <li>• <strong>Moderate correlation (0.7-0.9):</strong> Samples show good similarity</li>
          <li>• <strong>Low correlation (&lt;0.7):</strong> Samples may have different expression patterns</li>
          <li>• Replicates from the same condition should show high correlation</li>
          <li>• Dendrogram shows hierarchical clustering of samples based on correlation</li>
        </ul>
      </div>
    </div>
  );
};

export default WorkbenchDetailPCACorrelationHeatmap;
