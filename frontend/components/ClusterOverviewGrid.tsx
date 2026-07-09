import React, { useMemo, useRef, useState } from 'react';
import { ClusterInfo, ClusterPreview } from '../types';
import { ClusterMiniPattern } from './ClusterMiniPattern';

export interface ClusterOverviewItem extends ClusterInfo {
  is_merged?: boolean;
  source_cluster_ids?: string[];
  matched_source_ids?: string[];
}

interface ClusterOverviewGridProps {
  clusters: ClusterOverviewItem[];
  previewsByCluster: Record<string, ClusterPreview>;
  onSelectCluster: (clusterId: string) => void;
  onCreateMerge: (clusterIds: string[]) => Promise<{ mergedId: string } | null>;
  onUnmerge: (mergedId: string) => void;
  onResetMerges: () => void;
  highlightedClusterId?: string | null;
  onHoverCluster?: (clusterId: string | null) => void;
}

export function ClusterOverviewGrid({
  clusters,
  previewsByCluster,
  onSelectCluster,
  onCreateMerge,
  onUnmerge,
  onResetMerges,
  highlightedClusterId = null,
  onHoverCluster
}: ClusterOverviewGridProps) {
  const [mergeMode, setMergeMode] = useState(false);
  const [selectedForMerge, setSelectedForMerge] = useState<Set<string>>(new Set());
  const [isMerging, setIsMerging] = useState(false);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const mergeTargetRef = useRef<HTMLButtonElement | null>(null);
  const reducedMotion = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const sortedClusters = useMemo(() => {
    return [...clusters].sort((a, b) => {
      if (a.is_merged && !b.is_merged) return -1;
      if (!a.is_merged && b.is_merged) return 1;
      const getNumber = (id: string) => {
        const match = id.match(/\d+/);
        return match ? parseInt(match[0], 10) : Number.MAX_SAFE_INTEGER;
      };
      return getNumber(a.id) - getNumber(b.id);
    });
  }, [clusters]);

  const mergedClusters = useMemo(() => sortedClusters.filter((cluster) => cluster.is_merged), [sortedClusters]);

  const toggleSelect = (clusterId: string) => {
    setSelectedForMerge((prev) => {
      const next = new Set(prev);
      if (next.has(clusterId)) {
        next.delete(clusterId);
      } else {
        if (next.size >= 5) {
          alert('You can merge up to 5 clusters at once.');
          return prev;
        }
        next.add(clusterId);
      }
      return next;
    });
  };

  const animateMergeCards = async (clusterIds: string[]) => {
    if (reducedMotion || clusterIds.length === 0) return;
    const targetRect = mergeTargetRef.current?.getBoundingClientRect();
    if (!targetRect) return;

    const targetX = targetRect.left + (targetRect.width / 2);
    const targetY = targetRect.top + (targetRect.height / 2);
    const clones: HTMLElement[] = [];
    const animations: Promise<any>[] = [];

    clusterIds.forEach((clusterId, index) => {
      const sourceEl = cardRefs.current[clusterId];
      if (!sourceEl) return;

      const rect = sourceEl.getBoundingClientRect();
      const clone = sourceEl.cloneNode(true) as HTMLElement;
      clone.style.position = 'fixed';
      clone.style.left = `${rect.left}px`;
      clone.style.top = `${rect.top}px`;
      clone.style.width = `${rect.width}px`;
      clone.style.height = `${rect.height}px`;
      clone.style.margin = '0';
      clone.style.pointerEvents = 'none';
      clone.style.zIndex = '9999';
      clone.style.transformOrigin = 'center center';
      document.body.appendChild(clone);
      clones.push(clone);

      const dx = targetX - (rect.left + rect.width / 2) + ((index % 2 === 0 ? 8 : -8) * (index + 1));
      const dy = targetY - (rect.top + rect.height / 2);
      const rotate = index % 2 === 0 ? 12 : -12;

      const animation = clone.animate(
        [
          { transform: 'translate(0px, 0px) scale(1) rotate(0deg)', opacity: 1 },
          { transform: `translate(${dx * 0.75}px, ${dy * 0.75}px) scale(0.65) rotate(${rotate}deg)`, opacity: 0.8, offset: 0.7 },
          { transform: `translate(${dx}px, ${dy}px) scale(0.24) rotate(${rotate * 1.7}deg)`, opacity: 0.05 }
        ],
        {
          duration: 420,
          easing: 'cubic-bezier(0.22, 0.61, 0.36, 1)',
          fill: 'forwards'
        }
      );
      animations.push(animation.finished.catch(() => undefined));
    });

    const burst = document.createElement('div');
    burst.style.position = 'fixed';
    burst.style.left = `${targetX - 18}px`;
    burst.style.top = `${targetY - 18}px`;
    burst.style.width = '36px';
    burst.style.height = '36px';
    burst.style.border = '2px solid rgba(16,185,129,0.8)';
    burst.style.borderRadius = '9999px';
    burst.style.pointerEvents = 'none';
    burst.style.zIndex = '10000';
    document.body.appendChild(burst);
    const burstAnimation = burst.animate(
      [
        { transform: 'scale(0.3)', opacity: 0.0 },
        { transform: 'scale(1.1)', opacity: 0.95, offset: 0.4 },
        { transform: 'scale(1.8)', opacity: 0 }
      ],
      { duration: 320, easing: 'ease-out', fill: 'forwards' }
    );
    animations.push(burstAnimation.finished.catch(() => undefined));

    await Promise.all(animations);
    clones.forEach((clone) => clone.remove());
    burst.remove();
  };

  const handleMergeSelected = async () => {
    const selected = Array.from(selectedForMerge);
    if (selected.length < 2) return;

    try {
      setIsMerging(true);
      await animateMergeCards(selected);
      const result = await onCreateMerge(selected);
      if (!result) return;
      setSelectedForMerge(new Set());
    } catch (error: any) {
      alert(error?.message || 'Failed to merge selected clusters.');
    } finally {
      setIsMerging(false);
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <div className="flex items-center justify-between mb-4 gap-2">
        <div>
          <h3 className="text-lg font-semibold text-gray-800">Cluster Overview</h3>
          <span className="text-sm text-gray-500">{sortedClusters.length} cards ({mergedClusters.length} merged)</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setMergeMode((prev) => !prev);
              setSelectedForMerge(new Set());
            }}
            className={`px-3 py-1.5 text-sm rounded border ${mergeMode ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'}`}
          >
            {mergeMode ? 'Merge mode ON' : 'Merge mode'}
          </button>
          <button
            ref={mergeTargetRef}
            onClick={handleMergeSelected}
            disabled={!mergeMode || selectedForMerge.size < 2 || isMerging}
            className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            {isMerging ? 'Merging...' : `Merge selected (${selectedForMerge.size}/5)`}
          </button>
          <button
            onClick={onResetMerges}
            disabled={mergedClusters.length === 0}
            className="px-3 py-1.5 text-sm rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Reset all
          </button>
        </div>
      </div>

      <div className="pr-1">
        <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
          {sortedClusters.map((cluster) => {
            const preview = previewsByCluster[cluster.id];
            const isSelectedForMerge = selectedForMerge.has(cluster.id);
            const selectable = true;
            return (
              <div
                key={cluster.id}
                ref={(el) => { cardRefs.current[cluster.id] = el; }}
                data-cluster-id={cluster.id}
                onMouseEnter={() => onHoverCluster?.(cluster.id)}
                onMouseLeave={() => onHoverCluster?.(null)}
                onClick={() => (mergeMode && selectable ? toggleSelect(cluster.id) : onSelectCluster(cluster.id))}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    if (mergeMode && selectable) toggleSelect(cluster.id);
                    else onSelectCluster(cluster.id);
                  }
                }}
                role="button"
                tabIndex={0}
                className={`rounded-lg border p-3 text-left transition-all duration-300 cursor-pointer ${cluster.is_merged ? 'bg-emerald-50 border-emerald-200 hover:bg-emerald-100' : 'bg-white border-slate-200 hover:bg-slate-50 hover:border-slate-300'} ${isSelectedForMerge ? 'ring-2 ring-blue-500' : ''} ${highlightedClusterId === cluster.id ? 'ring-2 ring-amber-400 border-amber-300' : ''}`}
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-800">
                      {cluster.is_merged ? cluster.id.replace('merged_', 'Merged ') : cluster.id.replace('subcluster_', 'Cluster ')}
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {cluster.gene_count.toLocaleString()} genes
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {cluster.is_merged && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-600 text-white">MERGED</span>
                    )}
                    {mergeMode && selectable && (
                      <span className={`w-4 h-4 rounded border inline-flex items-center justify-center ${isSelectedForMerge ? 'bg-blue-600 border-blue-600 text-white' : 'border-slate-300 bg-white text-transparent'}`}>
                        V
                      </span>
                    )}
                  </div>
                </div>

                {cluster.is_merged && cluster.source_cluster_ids && (
                  <div className="text-[10px] text-slate-600 mb-2 truncate">
                    from {cluster.source_cluster_ids.map((id) => id.replace('subcluster_', 'C')).join(', ')}
                  </div>
                )}

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

                {cluster.is_merged && (
                  <div className="mt-2 flex justify-end">
                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        onUnmerge(cluster.id);
                      }}
                      className="text-xs px-2 py-1 rounded border border-slate-300 text-slate-600 hover:bg-white"
                    >
                      Unmerge
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
