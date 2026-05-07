import React from 'react';
import { useUserSettings } from '../contexts/UserSettingsContext';

export type GOProvider = 'david' | 'gprofiler';

interface GOProviderSubmenuProps {
  onSelect: (provider: GOProvider) => void;
  className?: string;
}

const GOProviderSubmenu: React.FC<GOProviderSubmenuProps> = ({ onSelect, className = '' }) => {
  const {
    settings: {
      go: { davidEmail }
    }
  } = useUserSettings();

  const davidEnabled = Boolean(davidEmail.trim());
  const disabledTooltip = 'Add your registered DAVID email in Settings -> AI Analysis to enable this provider.';
  const baseItemClass = 'block w-full px-4 py-2 text-left text-sm';

  return (
    <div className={`relative group ${className}`}>
      <button
        type="button"
        className={`${baseItemClass} flex items-center justify-between text-slate-700 hover:bg-slate-100`}
      >
        <span>GO Enrichment</span>
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>

      <div className="absolute left-full top-0 z-[60] hidden min-w-[12rem] rounded-md border border-slate-200 bg-white shadow-lg group-hover:block">
        {davidEnabled ? (
          <button
            type="button"
            onClick={() => onSelect('david')}
            className={`${baseItemClass} text-slate-700 hover:bg-slate-100`}
          >
            DAVID
          </button>
        ) : (
          <div
            title={disabledTooltip}
            className={`${baseItemClass} cursor-not-allowed bg-slate-50 text-slate-400`}
          >
            DAVID
          </div>
        )}
        <button
          type="button"
          onClick={() => onSelect('gprofiler')}
          className={`${baseItemClass} text-slate-700 hover:bg-slate-100`}
        >
          g:Profiler
        </button>
      </div>
    </div>
  );
};

export default GOProviderSubmenu;
