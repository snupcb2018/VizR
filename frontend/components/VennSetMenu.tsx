import React from 'react';

export interface VennSetSummary {
  index: number;
  name: string;
  count: number;
  isEmpty: boolean;
}

export const VENN_SET_COLORS = [
  {
    dot: 'bg-blue-500',
    text: 'text-blue-700',
    bg: 'bg-blue-50',
    border: 'border-blue-200',
  },
  {
    dot: 'bg-violet-500',
    text: 'text-violet-700',
    bg: 'bg-violet-50',
    border: 'border-violet-200',
  },
  {
    dot: 'bg-emerald-500',
    text: 'text-emerald-700',
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
  },
  {
    dot: 'bg-amber-500',
    text: 'text-amber-700',
    bg: 'bg-amber-50',
    border: 'border-amber-200',
  },
] as const;

function getSetColor(index: number, isEmpty: boolean) {
  if (isEmpty) {
    return {
      dot: 'bg-slate-300',
      text: 'text-slate-500',
      bg: 'bg-slate-50',
      border: 'border-slate-200',
    };
  }

  return VENN_SET_COLORS[index] ?? VENN_SET_COLORS[0];
}

interface VennSetMenuProps {
  summaries?: VennSetSummary[];
  onSelectSet: (targetSetIndex: number) => void;
  className?: string;
}

export default function VennSetMenu({
  summaries,
  onSelectSet,
  className = '',
}: VennSetMenuProps) {
  const fallbackSummaries = Array.from({ length: 4 }, (_, index) => ({
    index,
    name: `Set ${String.fromCharCode(65 + index)}`,
    count: 0,
    isEmpty: true,
  }));
  const items = summaries && summaries.length > 0 ? summaries : fallbackSummaries;

  return (
    <div className={`relative group ${className}`}>
      <div className="flex items-center justify-between px-4 py-2 text-sm text-slate-700 hover:bg-slate-100 cursor-default select-none">
        <span>Venn Diagram</span>
        <svg className="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
        </svg>
      </div>

      <div className="absolute top-0 left-full hidden min-w-[180px] rounded-md border border-slate-200 bg-white shadow-lg z-50 group-hover:block">
        {items.map((summary) => {
          const color = getSetColor(summary.index, summary.isEmpty);
          return (
            <button
              key={summary.index}
              type="button"
              onClick={() => onSelectSet(summary.index)}
              className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-sm hover:bg-slate-50 ${summary.index === 0 ? 'rounded-t-md' : ''} ${summary.index === items.length - 1 ? 'rounded-b-md' : ''}`}
            >
              <span className="flex items-center gap-2 min-w-0">
                <span className={`h-2.5 w-2.5 rounded-full ${color.dot}`} />
                <span className={`truncate ${color.text}`}>{summary.name}</span>
              </span>
              <span className={`rounded-full border px-2 py-0.5 text-xs ${color.bg} ${color.border} ${color.text}`}>
                {summary.count.toLocaleString()}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
