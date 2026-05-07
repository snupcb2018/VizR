import React, { useEffect, useMemo, useState } from 'react';
import Plot from 'react-plotly.js';
import { TreeCuttingDendrogramData } from '../types';

interface TreeClusterDendrogramPanelProps {
  data: TreeCuttingDendrogramData | null;
  isLoading: boolean;
  error: string | null;
  isOpen: boolean;
  onToggleOpen: () => void;
  currentPtree: number;
  onApplyPtree: (ptree: number) => void;
  highlightedClusterId?: string | null;
  onHoverCluster?: (clusterId: string | null) => void;
  onSelectCluster?: (clusterId: string) => void;
  plotHeight?: number;
}

const clampPtree = (value: number) => Math.max(1, Math.min(100, Math.round(value)));

export function TreeClusterDendrogramPanel({
  data,
  isLoading,
  error,
  isOpen,
  onToggleOpen,
  currentPtree,
  onApplyPtree,
  highlightedClusterId = null,
  onHoverCluster,
  onSelectCluster,
  plotHeight = 320
}: TreeClusterDendrogramPanelProps) {
  const [draftPtree, setDraftPtree] = useState<number>(currentPtree);

  useEffect(() => {
    setDraftPtree(currentPtree);
  }, [currentPtree]);

  const plotModel = useMemo(() => {
    if (!data || data.status !== 'available' || !data.dendrogram || !data.clusters || !data.leaf_order || !data.y_range) {
      return null;
    }

    const convertX = (coord: number) => (coord - 5) / 10;
    const xValues: Array<number | null> = [];
    const yValues: Array<number | null> = [];

    data.dendrogram.icoord.forEach((icoord, index) => {
      const dcoord = data.dendrogram?.dcoord[index] || [];
      for (let i = 0; i < icoord.length; i++) {
        xValues.push(convertX(icoord[i]));
        yValues.push(dcoord[i] ?? 0);
      }
      xValues.push(null);
      yValues.push(null);
    });

    const orderedClusters = data.leaf_order.map((leafIndex) => data.clusters![leafIndex]).filter(Boolean);
    const leafX = orderedClusters.map((_, idx) => idx);
    const yMin = data.y_range.min;
    const yMax = data.y_range.max;

    const ptreeToY = (ptree: number) => {
      if (yMax <= yMin) return yMin;
      return yMin + ((clampPtree(ptree) - 1) / 99) * (yMax - yMin);
    };
    const yToPtree = (y: number) => {
      if (yMax <= yMin) return 1;
      const ratio = (y - yMin) / (yMax - yMin);
      return clampPtree(1 + (ratio * 99));
    };

    return {
      xValues,
      yValues,
      orderedClusters,
      leafX,
      yMin,
      yMax,
      ptreeToY,
      yToPtree
    };
  }, [data]);

  const canApply = draftPtree !== clampPtree(currentPtree);

  return (
    <div className="h-full bg-white rounded-lg border border-gray-200 shadow-sm">
      <button
        onClick={onToggleOpen}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
      >
        <div className="text-left">
          <h3 className="text-base font-semibold text-gray-800">Dendrogram (Cluster-level)</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            {data?.method ? `${data.method.distance} / ${data.method.linkage}` : '1-pearson / average'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-600">Current ptree: <b>{currentPtree}</b></span>
          <svg className={`w-4 h-4 text-gray-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {isOpen && (
        <div className="h-[calc(100%-72px)] px-4 pb-4 border-t border-gray-100 overflow-hidden">
          {isLoading && (
            <div className="py-10 text-sm text-gray-500">Loading dendrogram...</div>
          )}

          {!isLoading && error && (
            <div className="py-6 text-sm text-red-600">{error}</div>
          )}

          {!isLoading && !error && data?.status === 'not_available' && (
            <div className="py-6 text-sm text-gray-600">No clustering output found for current parameters.</div>
          )}

          {!isLoading && !error && data?.status === 'insufficient_clusters' && (
            <div className="py-6 text-sm text-gray-600">Need at least 2 clusters to draw dendrogram.</div>
          )}

          {!isLoading && !error && plotModel && (
            <>
              <div className="mt-3">
                <Plot
                  data={[
                    {
                      type: 'scatter',
                      mode: 'lines',
                      x: plotModel.xValues,
                      y: plotModel.yValues,
                      line: { color: '#1f2937', width: 1.6 },
                      hoverinfo: 'none',
                      name: 'dendrogram',
                      showlegend: false
                    } as any,
                    {
                      type: 'scatter',
                      mode: 'markers',
                      x: plotModel.leafX,
                      y: plotModel.leafX.map(() => plotModel.yMin),
                      customdata: plotModel.orderedClusters,
                      marker: {
                        size: plotModel.orderedClusters.map((clusterId) => (clusterId === highlightedClusterId ? 10 : 6)),
                        color: plotModel.orderedClusters.map((clusterId) => (clusterId === highlightedClusterId ? '#f59e0b' : '#475569')),
                        line: { width: 1, color: '#ffffff' }
                      },
                      hovertemplate: '<b>%{customdata}</b><extra></extra>',
                      name: 'leaves',
                      showlegend: false
                    } as any
                  ]}
                  layout={{
                    autosize: true,
                    height: plotHeight,
                    margin: { l: 56, r: 24, t: 20, b: 90 },
                    title: { text: ' ' },
                    paper_bgcolor: 'white',
                    plot_bgcolor: 'white',
                    hovermode: 'closest',
                    xaxis: {
                      title: { text: 'Clusters' },
                      tickmode: 'array',
                      tickvals: plotModel.leafX,
                      ticktext: plotModel.orderedClusters,
                      tickangle: -35,
                      showgrid: false,
                      zeroline: false
                    },
                    yaxis: {
                      title: { text: 'Distance (1 - Pearson)' },
                      showgrid: true,
                      gridcolor: '#e5e7eb',
                      zeroline: false
                    },
                    shapes: [
                      {
                        type: 'line',
                        xref: 'paper',
                        x0: 0,
                        x1: 1,
                        yref: 'y',
                        y0: plotModel.ptreeToY(draftPtree),
                        y1: plotModel.ptreeToY(draftPtree),
                        line: { color: '#ef4444', width: 2, dash: 'dash' }
                      }
                    ]
                  }}
                  config={{
                    displayModeBar: false,
                    responsive: true,
                    editable: true,
                    edits: { shapePosition: true }
                  }}
                  useResizeHandler
                  style={{ width: '100%' }}
                  onHover={(event) => {
                    const point = event?.points?.[0];
                    if (!point) return;
                    const clusterId = point.customdata as string | undefined;
                    if (clusterId) onHoverCluster?.(clusterId);
                  }}
                  onUnhover={() => {
                    onHoverCluster?.(null);
                  }}
                  onClick={(event) => {
                    const point = event?.points?.[0];
                    if (!point) return;
                    const clusterId = point.customdata as string | undefined;
                    if (clusterId) onSelectCluster?.(clusterId);
                  }}
                  onRelayout={(relayoutData: any) => {
                    const y0 = relayoutData?.['shapes[0].y0'];
                    const y1 = relayoutData?.['shapes[0].y1'];
                    if (typeof y0 === 'number' || typeof y1 === 'number') {
                      const y = typeof y0 === 'number' && typeof y1 === 'number'
                        ? (y0 + y1) / 2
                        : (typeof y0 === 'number' ? y0 : y1);
                      setDraftPtree(plotModel.yToPtree(y));
                    }
                  }}
                />
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-3">
                <span className="text-sm text-gray-600">Draft ptree</span>
                <input
                  type="range"
                  min={1}
                  max={100}
                  value={draftPtree}
                  onChange={(event) => setDraftPtree(clampPtree(parseInt(event.target.value, 10)))}
                  className="w-60"
                />
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={draftPtree}
                  onChange={(event) => setDraftPtree(clampPtree(parseInt(event.target.value || '1', 10)))}
                  className="w-20 px-2 py-1 text-sm border border-gray-300 rounded"
                />
                <button
                  onClick={() => onApplyPtree(draftPtree)}
                  disabled={!canApply}
                  className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white disabled:bg-gray-300 disabled:cursor-not-allowed"
                >
                  Apply
                </button>
                <span className="text-xs text-gray-500">
                  Drag the red line or use slider, then apply.
                </span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
