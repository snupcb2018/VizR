import React, { useState, useEffect, useRef } from 'react';

// ========================================
// Type Definitions
// ========================================

export interface ColumnFilter {
    operator: 'gt' | 'gte' | 'lt' | 'lte' | 'eq';
    value: string;
}

interface ColumnFilterPopupProps {
    isOpen: boolean;
    onClose: () => void;
    columnName: string;
    currentFilter?: ColumnFilter;
    currentSort?: 'asc' | 'desc';
    onApply: (filter: ColumnFilter | null, sort: 'asc' | 'desc' | null) => void;
}

// ========================================
// Main Component
// ========================================

const ColumnFilterPopup: React.FC<ColumnFilterPopupProps> = ({
    isOpen,
    onClose,
    columnName,
    currentFilter,
    currentSort,
    onApply
}) => {
    const popupRef = useRef<HTMLDivElement>(null);
    const [sortOption, setSortOption] = useState<'asc' | 'desc' | ''>('');
    const [filterOperator, setFilterOperator] = useState<ColumnFilter['operator'] | ''>('');
    const [filterValue, setFilterValue] = useState('');

    // Initialize state from current filter/sort
    useEffect(() => {
        if (isOpen) {
            setSortOption(currentSort || '');
            setFilterOperator(currentFilter?.operator || '');
            setFilterValue(currentFilter?.value || '');
        }
    }, [isOpen, currentFilter, currentSort]);

    // Close on outside click
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (popupRef.current && !popupRef.current.contains(event.target as Node)) {
                onClose();
            }
        };

        if (isOpen) {
            document.addEventListener('mousedown', handleClickOutside);
        }

        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    const handleApply = () => {
        const filter: ColumnFilter | null =
            filterOperator && filterValue
                ? { operator: filterOperator, value: filterValue }
                : null;

        const sort = sortOption || null;

        onApply(filter, sort);
        onClose();
    };

    const handleClear = () => {
        setSortOption('');
        setFilterOperator('');
        setFilterValue('');
        onApply(null, null);
        onClose();
    };

    return (
        <div
            ref={popupRef}
            className="absolute top-full mt-2 right-0 z-50 bg-white rounded-lg shadow-xl border border-slate-200 p-3 w-64"
            style={{ minWidth: '256px' }}
        >
            {/* Header */}
            <div className="flex items-center justify-between mb-3 pb-3 border-b border-slate-200">
                <h4 className="font-semibold text-sm text-slate-900">
                    Filter & Sort: {columnName}
                </h4>
                <button
                    onClick={onClose}
                    className="text-slate-400 hover:text-slate-600 transition-colors"
                >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>

            {/* Sort Options */}
            <div className="mb-4 pb-4 border-b border-slate-200">
                <h5 className="font-semibold text-xs text-slate-700 mb-2 uppercase">Sort</h5>
                <div className="space-y-2">
                    <label className="flex items-center cursor-pointer hover:bg-slate-50 p-2 rounded transition-colors">
                        <input
                            type="radio"
                            name="sort"
                            value="asc"
                            checked={sortOption === 'asc'}
                            onChange={(e) => setSortOption(e.target.value as 'asc')}
                            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-slate-300"
                        />
                        <span className="ml-3 text-sm text-slate-700">Ascending</span>
                    </label>
                    <label className="flex items-center cursor-pointer hover:bg-slate-50 p-2 rounded transition-colors">
                        <input
                            type="radio"
                            name="sort"
                            value="desc"
                            checked={sortOption === 'desc'}
                            onChange={(e) => setSortOption(e.target.value as 'desc')}
                            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-slate-300"
                        />
                        <span className="ml-3 text-sm text-slate-700">Descending</span>
                    </label>
                </div>
            </div>

            {/* Filter Options */}
            <div className="mb-4">
                <h5 className="font-semibold text-xs text-slate-700 mb-2 uppercase">Filter by Value</h5>
                <div className="space-y-3">
                    <select
                        value={filterOperator}
                        onChange={(e) => setFilterOperator(e.target.value as ColumnFilter['operator'] | '')}
                        className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    >
                        <option value="">No filter</option>
                        <option value="gt">Greater than (&gt;)</option>
                        <option value="gte">Greater than or equal (≥)</option>
                        <option value="lt">Less than (&lt;)</option>
                        <option value="lte">Less than or equal (≤)</option>
                        <option value="eq">Equal to (=)</option>
                    </select>

                    {filterOperator && (
                        <input
                            type="number"
                            step="any"
                            placeholder="Enter value..."
                            value={filterValue}
                            onChange={(e) => setFilterValue(e.target.value)}
                            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                        />
                    )}
                </div>
            </div>

            {/* Action Buttons */}
            <div className="flex justify-end space-x-2 pt-4 border-t border-slate-200">
                <button
                    onClick={handleClear}
                    className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
                >
                    Clear
                </button>
                <button
                    onClick={handleApply}
                    className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
                >
                    Apply
                </button>
            </div>
        </div>
    );
};

export default ColumnFilterPopup;
