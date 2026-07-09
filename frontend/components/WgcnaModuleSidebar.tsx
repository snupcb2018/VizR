import React, { useMemo, useRef } from 'react';
import { WgcnaModuleInfo, WgcnaModulePreview } from '../types';
import { ClusterMiniPattern } from './ClusterMiniPattern';

interface WgcnaModuleSidebarProps {
  modules: WgcnaModuleInfo[];
  selectedModule: string | null;
  onSelectModule: (moduleId: string) => void;
  onSelectOverview: () => void;
  onSearch: (query: string) => void;
  isSearchResult: boolean;
  searchQuery: string;
  previewsByModule: Record<string, WgcnaModulePreview>;
}

// WGCNA module color to CSS color mapping
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
  gray: '#808080',
  lightyellow: '#FFFFE0',
  darkred: '#8B0000',
  darkgreen: '#006400',
  darkgrey: '#A9A9A9',
  darkturquoise: '#00CED1',
  orange: '#FFA500',
  darkorange: '#FF8C00',
  white: '#FFFFFF',
  royalblue: '#4169E1',
  lightgreen: '#90EE90',
  darkgray: '#A9A9A9',
  skyblue: '#87CEEB'
};

export const WgcnaModuleSidebar = React.memo(function WgcnaModuleSidebar({
  modules,
  selectedModule,
  onSelectModule,
  onSelectOverview,
  onSearch,
  isSearchResult,
  searchQuery,
  previewsByModule
}: WgcnaModuleSidebarProps) {
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Sort modules by gene count (descending)
  const sortedModules = useMemo(() => {
    return [...modules].sort((a, b) => b.gene_count - a.gene_count);
  }, [modules]);

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
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
          </svg>
          <h3 className="text-lg font-semibold text-gray-800">Modules ({modules.length})</h3>
        </div>
        <p className="text-xs text-gray-500 mt-1">Co-expression gene modules</p>

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
              <span>Showing modules with: <strong>{searchQuery}</strong></span>
            </div>
          )}
        </div>
      </div>
      <div className="overflow-y-auto max-h-[calc(100vh-200px)]">
        <div className="space-y-1 p-2">
          {modules.length > 0 && (
            <button
              onClick={onSelectOverview}
              className={`
                w-full text-left px-3 py-3 rounded-md transition-colors duration-200 border
                ${selectedModule === null
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-700 hover:bg-gray-50 border-transparent'}
              `}
            >
              <div className="font-medium text-sm">Overview</div>
              <div className={`text-xs mt-1 ${selectedModule === null ? 'text-blue-100' : 'text-gray-500'}`}>
                All modules preview
              </div>
            </button>
          )}

          {sortedModules.map((module) => {
            const colorHex = moduleColorMap[module.id.toLowerCase()] || '#808080';
            const isSelected = selectedModule === module.id;
            const preview = previewsByModule[module.id];

            return (
              <button
                key={module.id}
                onClick={() => onSelectModule(module.id)}
                className={`
                  w-full text-left px-3 py-3 rounded-md transition-all duration-200 border
                  ${
                    isSelected
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-700 hover:bg-gray-50 border-transparent'
                  }
                `}
              >
                <div className="flex items-center gap-2">
                  <div
                    className="w-4 h-4 rounded-sm border flex-shrink-0"
                    style={{
                      backgroundColor: colorHex,
                      borderColor: isSelected ? '#bfdbfe' : '#d1d5db'
                    }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-sm truncate">
                      {module.id.charAt(0).toUpperCase() + module.id.slice(1)}
                    </div>
                    <div className={`text-xs mt-1 ${
                      isSelected ? 'text-blue-100' : 'text-gray-500'
                    }`}>
                      {module.gene_count.toLocaleString()} genes
                    </div>
                  </div>
                  {preview && (
                    <ClusterMiniPattern
                      mean={preview.statistics.mean}
                      median={preview.statistics.median}
                      width={82}
                      height={30}
                      className="shrink-0"
                    />
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Empty state */}
      {modules.length === 0 && (
        <div className="p-8 text-center text-gray-400">
          <svg className="w-12 h-12 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
          </svg>
          {isSearchResult ? (
            <>
              <p className="text-sm">No modules found</p>
              <p className="text-xs mt-1">No modules contain gene: <strong>{searchQuery}</strong></p>
              <button
                onClick={handleClearSearch}
                className="mt-3 text-xs text-blue-600 hover:text-blue-700 underline"
              >
                Clear search
              </button>
            </>
          ) : (
            <>
              <p className="text-sm">No modules found</p>
              <p className="text-xs mt-1">Run WGCNA analysis first</p>
            </>
          )}
        </div>
      )}
    </div>
  );
});
