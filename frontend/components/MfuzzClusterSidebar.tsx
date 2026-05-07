import React, { useMemo, useRef } from 'react';
import { MfuzzClusterInfo, MfuzzClusterPreview } from '../types';
import { ClusterMiniPattern } from './ClusterMiniPattern';

interface MfuzzClusterSidebarProps {
  clusters: MfuzzClusterInfo[];
  selectedCluster: number | null;
  onSelectCluster: (clusterId: number) => void;
  onSelectOverview: () => void;
  onSearch: (query: string) => void;
  isSearchResult: boolean;
  searchQuery: string;
  previewsByCluster: Record<number, MfuzzClusterPreview>;
}

export const MfuzzClusterSidebar = React.memo(function MfuzzClusterSidebar({
  clusters,
  selectedCluster,
  onSelectCluster,
  onSelectOverview,
  onSearch,
  isSearchResult,
  searchQuery,
  previewsByCluster
}: MfuzzClusterSidebarProps) {
  const searchInputRef = useRef<HTMLInputElement>(null);

  // 클러스터 ID를 오름차순으로 정렬
  const sortedClusters = useMemo(() => {
    return [...clusters].sort((a, b) => a.id - b.id);
  }, [clusters]);

  const handleSearch = () => {
    const query = searchInputRef.current?.value.trim() || '';
    onSearch(query);
  };

  const handleClearSearch = () => {
    if (searchInputRef.current) {
      searchInputRef.current.value = '';
    }
    onSearch('');
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm sticky top-4">
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <svg className="w-5 h-5 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <h3 className="text-lg font-semibold text-gray-800">Clusters ({clusters.length})</h3>
        </div>
        <p className="text-xs text-gray-500 mt-1">Temporal expression clusters</p>

        {/* Search box */}
        <div className="mt-3">
          <div className="flex gap-1">
            <div className="flex-1 relative">
              <input
                ref={searchInputRef}
                type="text"
                placeholder="Search by gene..."
                defaultValue={searchQuery}
                onKeyPress={handleKeyPress}
                className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 pr-8"
              />
              {isSearchResult && (
                <button
                  onClick={handleClearSearch}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  title="Clear search"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>
            <button
              onClick={handleSearch}
              className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </button>
          </div>

          {/* Search result indicator */}
          {isSearchResult && (
            <div className="mt-2 text-xs text-blue-600 flex items-center gap-1">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Showing clusters with: <strong>{searchQuery}</strong></span>
            </div>
          )}
        </div>
      </div>
      <div className="overflow-y-auto max-h-[calc(100vh-200px)]">
        <div className="space-y-1 p-2">
          {clusters.length > 0 && (
            <button
              onClick={onSelectOverview}
              className={`
                w-full text-left px-3 py-3 rounded-md transition-colors duration-200 border
                ${selectedCluster === null
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-700 hover:bg-gray-50 border-transparent'}
              `}
            >
              <div className="font-medium text-sm">Overview</div>
              <div className={`text-xs mt-1 ${selectedCluster === null ? 'text-blue-100' : 'text-gray-500'}`}>
                All clusters preview
              </div>
            </button>
          )}

          {sortedClusters.map((cluster) => (
            <button
              key={cluster.id}
              onClick={() => onSelectCluster(cluster.id)}
              className={`
                w-full text-left px-3 py-3 rounded-md transition-colors duration-200 border
                ${
                  selectedCluster === cluster.id
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-700 hover:bg-gray-50 border-transparent'
                }
              `}
            >
              <div className="flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-sm">
                    Cluster {cluster.id}
                  </div>
                  <div
                    className={`text-xs mt-1 ${
                      selectedCluster === cluster.id ? 'text-blue-100' : 'text-gray-500'
                    }`}
                  >
                    {cluster.gene_count.toLocaleString()} genes
                  </div>
                </div>
                {previewsByCluster[cluster.id] && (
                  <ClusterMiniPattern
                    mean={previewsByCluster[cluster.id].statistics.mean}
                    median={previewsByCluster[cluster.id].statistics.median}
                    width={82}
                    height={30}
                    className="shrink-0"
                  />
                )}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Empty state */}
      {clusters.length === 0 && (
        <div className="p-8 text-center text-gray-400">
          <svg className="w-12 h-12 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
          </svg>
          {isSearchResult ? (
            <>
              <p className="text-sm">No clusters found</p>
              <p className="text-xs mt-1">No clusters contain gene: <strong>{searchQuery}</strong></p>
              <button
                onClick={handleClearSearch}
                className="mt-3 text-xs text-blue-600 hover:text-blue-700 underline"
              >
                Clear search
              </button>
            </>
          ) : (
            <>
              <p className="text-sm">No clusters found</p>
              <p className="text-xs mt-1">Run Mfuzz clustering first</p>
            </>
          )}
        </div>
      )}
    </div>
  );
});
