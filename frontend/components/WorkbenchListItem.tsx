
import React from 'react';
import { Workbench } from '../types';
import StatusBadge from './StatusBadge';

interface WorkbenchListItemProps {
  workbench: Workbench;
  onSelect: (workbench: Workbench) => void;
  onMethodClick?: () => void;
}

export default function WorkbenchListItem({ workbench, onSelect, onMethodClick }: WorkbenchListItemProps): React.ReactNode {
  return (
    <tr
      onClick={() => onSelect(workbench)}
      className="border-b border-slate-200 hover:bg-slate-100 cursor-pointer transition-colors duration-150"
    >
      <td className="p-4">
        <div className="font-semibold text-slate-700">{workbench.name}</div>
        <div className="text-sm text-slate-500">ID: {workbench.id}</div>
      </td>
      <td className="p-4">
        <StatusBadge status={workbench.status} />
      </td>
      <td className="p-4 text-slate-500">{workbench.createdAt}</td>
      <td className="p-4 text-slate-500">{workbench.lastUpdated}</td>
      <td className="p-4 text-center">
        {onMethodClick ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onMethodClick();
            }}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-primary bg-primary/10 rounded-lg hover:bg-primary/20 transition-colors"
            title="Generate Method section text for paper"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Method
          </button>
        ) : (
          <span className="text-xs text-slate-400" title="Pipeline must be completed to generate method text">
            —
          </span>
        )}
      </td>
    </tr>
  );
}
