import React, { useMemo } from 'react';
import { MfuzzClusterInfo, MfuzzClusterPreview } from '../types';
import { ClusterMiniPattern } from './ClusterMiniPattern';

interface MfuzzClusterOverviewGridProps {
  clusters: MfuzzClusterInfo[];
  previewsByCluster: Record<number, MfuzzClusterPreview>;
  onSelectCluster: (clusterId: number) => void;
}

export function MfuzzClusterOverviewGrid({
  clusters,
  previewsByCluster,
  onSelectCluster
}: MfuzzClusterOverviewGridProps) {
  const sortedClusters = useMemo(() => [...clusters].sort((a, b) => a.id - b.id), [clusters]);

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-800">Cluster Overview</h3>
        <span className="text-sm text-gray-500">{sortedClusters.length} clusters</span>
      </div>

      <div className="max-h-[calc(100vh-220px)] overflow-y-auto pr-1">
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}
        >
          {sortedClusters.map((cluster) => {
            const preview = previewsByCluster[cluster.id];
            return (
              <button
                key={cluster.id}
                onClick={() => onSelectCluster(cluster.id)}
                className="rounded-lg border border-slate-200 bg-white p-3 text-left transition-colors hover:bg-slate-50 hover:border-slate-300"
              >
                <div className="mb-2">
                  <div className="font-semibold text-slate-800">
                    Cluster {cluster.id}
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {cluster.gene_count.toLocaleString()} genes
                  </div>
                </div>

                {preview ? (
                  <ClusterMiniPattern
                    mean={preview.statistics.mean}
                    median={preview.statistics.median}
                    width={210}
                    height={64}
                  />
                ) : (
                  <div className="h-16 rounded border border-slate-200 bg-slate-50 flex items-center justify-center text-xs text-slate-400">
                    Preview loading...
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

