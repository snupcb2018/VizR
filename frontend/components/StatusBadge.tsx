
import React from 'react';

interface StatusBadgeProps {
  status: string;
}

export default function StatusBadge({ status }: StatusBadgeProps): React.ReactNode {
  const baseClasses = 'px-3 py-1 text-xs font-medium rounded-full inline-flex items-center';

  const statusStyles: Record<string, string> = {
    'running': 'bg-cyan-100 text-cyan-800 animate-pulse',
    'completed': 'bg-emerald-100 text-emerald-800',
    'failed': 'bg-rose-100 text-rose-800',
    'pending': 'bg-amber-100 text-amber-800',
  };

  const statusDotStyles: Record<string, string> = {
    'running': 'bg-cyan-500',
    'completed': 'bg-emerald-500',
    'failed': 'bg-rose-500',
    'pending': 'bg-amber-500',
  };

  const statusLabels: Record<string, string> = {
    'running': 'Running',
    'completed': 'Completed',
    'failed': 'Failed',
    'pending': 'Pending',
  };

  const currentStatus = status?.toLowerCase() || 'pending';
  
  return (
    <span className={`${baseClasses} ${statusStyles[currentStatus] || statusStyles['pending']}`}>
        <span className={`w-2 h-2 mr-2 rounded-full ${statusDotStyles[currentStatus] || statusDotStyles['pending']}`}></span>
        {statusLabels[currentStatus] || 'Unknown'}
    </span>
  );
}
