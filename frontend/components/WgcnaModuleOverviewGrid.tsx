import React, { useMemo } from 'react';
import { WgcnaModuleInfo, WgcnaModulePreview } from '../types';
import { ClusterMiniPattern } from './ClusterMiniPattern';

interface WgcnaModuleOverviewGridProps {
  modules: WgcnaModuleInfo[];
  previewsByModule: Record<string, WgcnaModulePreview>;
  onSelectModule: (moduleId: string) => void;
}

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

export function WgcnaModuleOverviewGrid({
  modules,
  previewsByModule,
  onSelectModule
}: WgcnaModuleOverviewGridProps) {
  const sortedModules = useMemo(
    () => [...modules].sort((a, b) => b.gene_count - a.gene_count),
    [modules]
  );

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-800">Module Overview</h3>
        <span className="text-sm text-gray-500">{sortedModules.length} modules</span>
      </div>

      <div className="max-h-[calc(100vh-220px)] overflow-y-auto pr-1">
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}
        >
          {sortedModules.map((module) => {
            const preview = previewsByModule[module.id];
            const colorHex = moduleColorMap[module.id.toLowerCase()] || '#808080';

            return (
              <button
                key={module.id}
                onClick={() => onSelectModule(module.id)}
                className="rounded-lg border border-slate-200 bg-white p-3 text-left transition-colors hover:bg-slate-50 hover:border-slate-300"
              >
                <div className="mb-2 flex items-center gap-2">
                  <div
                    className="w-4 h-4 rounded-sm border"
                    style={{ backgroundColor: colorHex, borderColor: '#d1d5db' }}
                  />
                  <div>
                    <div className="font-semibold text-slate-800 capitalize">
                      {module.id}
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {module.gene_count.toLocaleString()} genes
                    </div>
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
