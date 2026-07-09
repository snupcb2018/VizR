import React, { useEffect, useRef, useState } from 'react';
import CopyGeneListMenuItem from './CopyGeneListMenuItem';
import GOProviderSubmenu, { GOProvider } from './GOProviderSubmenu';

interface SelectableGeneTableShellProps {
  selectedGenes: string[];
  leftControls?: React.ReactNode;
  afterAnalyzeControls?: React.ReactNode;
  rightControls?: React.ReactNode;
  onHeatmap?: () => void;
  heatmapLabel?: string;
  onGOAnalysis?: (provider: GOProvider) => void | Promise<void>;
  onKEGG?: () => void;
  vennMenu?: React.ReactNode;
  extraMenuItems?: React.ReactNode;
  toolbarClassName?: string;
  leftGroupClassName?: string;
  rightGroupClassName?: string;
  analyzeButtonClassName?: string;
  menuClassName?: string;
  analyzeLabel?: string;
}

const DEFAULT_ANALYZE_BUTTON_CLASS =
  'px-4 py-2 text-sm font-semibold bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed flex items-center';
const DEFAULT_TOOLBAR_CLASS = 'flex items-center justify-between gap-4';
const DEFAULT_LEFT_GROUP_CLASS = 'flex flex-wrap items-center gap-4';
const DEFAULT_RIGHT_GROUP_CLASS = 'flex items-center gap-4';
const DEFAULT_MENU_CLASS =
  'absolute top-full right-0 mt-2 w-48 bg-white rounded-md shadow-lg z-50 border border-slate-200';

export default function SelectableGeneTableShell({
  selectedGenes,
  leftControls,
  afterAnalyzeControls,
  rightControls,
  onHeatmap,
  heatmapLabel = 'Heatmap',
  onGOAnalysis,
  onKEGG,
  vennMenu,
  extraMenuItems,
  toolbarClassName = DEFAULT_TOOLBAR_CLASS,
  leftGroupClassName = DEFAULT_LEFT_GROUP_CLASS,
  rightGroupClassName = DEFAULT_RIGHT_GROUP_CLASS,
  analyzeButtonClassName = DEFAULT_ANALYZE_BUTTON_CLASS,
  menuClassName = DEFAULT_MENU_CLASS,
  analyzeLabel = 'Analyze',
}: SelectableGeneTableShellProps) {
  const [isActionMenuOpen, setActionMenuOpen] = useState(false);
  const actionMenuRef = useRef<HTMLDivElement>(null);
  const selectedCount = selectedGenes.length;

  useEffect(() => {
    const handleOutsideClick = (event: MouseEvent) => {
      if (actionMenuRef.current && !actionMenuRef.current.contains(event.target as Node)) {
        setActionMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const closeMenu = () => setActionMenuOpen(false);

  const handleHeatmap = () => {
    onHeatmap?.();
    closeMenu();
  };

  const handleGOAnalysis = async (provider: GOProvider) => {
    if (!onGOAnalysis) {
      return;
    }
    await Promise.resolve(onGOAnalysis(provider));
    closeMenu();
  };

  const handleKEGG = () => {
    onKEGG?.();
    closeMenu();
  };

  return (
    <div className={toolbarClassName}>
      <div className={leftGroupClassName}>
        {leftControls}
        <div className="relative" ref={actionMenuRef}>
          <button
            type="button"
            onClick={() => setActionMenuOpen((prev) => !prev)}
            disabled={selectedCount === 0}
            className={analyzeButtonClassName}
          >
            {analyzeLabel} ({selectedCount})
            <svg className="ml-2 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {isActionMenuOpen && (
            <div className={menuClassName}>
              {onHeatmap && (
                <button
                  type="button"
                  onClick={handleHeatmap}
                  className="block w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-100"
                >
                  {heatmapLabel}
                </button>
              )}
              {onGOAnalysis && <GOProviderSubmenu onSelect={(provider) => { void handleGOAnalysis(provider); }} />}
              {onKEGG && (
                <button
                  type="button"
                  onClick={handleKEGG}
                  className="block w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-100"
                >
                  KEGG Pathway
                </button>
              )}
              {vennMenu}
              {extraMenuItems}
              <CopyGeneListMenuItem genes={selectedGenes} onCopied={closeMenu} />
            </div>
          )}
        </div>
        {afterAnalyzeControls}
      </div>
      {rightControls ? <div className={rightGroupClassName}>{rightControls}</div> : null}
    </div>
  );
}
