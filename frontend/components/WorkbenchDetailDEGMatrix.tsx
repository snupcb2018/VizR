import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { apiService } from '../services/api';
import CopyGeneListMenuItem from './CopyGeneListMenuItem';
import SelectableGeneTableShell from './SelectableGeneTableShell';

// ========================================
// Type Definitions
// ========================================

interface WorkbenchDetailDEGMatrixProps {
    workbenchId: number;
    comparisonName: string;
    toolName: string;
    selectedGenes: Set<string>;
    onSelectionChange: (genes: Set<string>) => void;
    onAnalysisRequest: (type: string) => void;
    showComingSoon: () => void;
}

// ========================================
// Constants
// ========================================

const GENE_SETS = [
    'Abscission_Zone',
    'carbohydrates',
    'cell_wall_general',
    'secondary_cell_wall',
    'ROS',
    'death',
    'lipid_general',
    'signaling_general',
    'TF',
    'epigenetics',
    'hormone',
    'meristem'
];

// ========================================
// Utility Hooks
// ========================================

const useTableHeight = () => {
    const [tableHeight, setTableHeight] = useState('60vh');

    useEffect(() => {
        const calculateHeight = () => {
            const viewportHeight = window.innerHeight;
            const headerHeight = 120;
            const tabsHeight = 180; // Increased for sidebar + tabs
            const paddingHeight = 100;
            const toolbarHeight = 80;

            const availableHeight = viewportHeight - headerHeight - tabsHeight - paddingHeight - toolbarHeight;
            const minHeight = Math.max(300, availableHeight);
            const maxHeight = Math.min(viewportHeight * 0.8, minHeight);

            setTableHeight(`${maxHeight}px`);
        };

        calculateHeight();
        window.addEventListener('resize', calculateHeight);

        return () => window.removeEventListener('resize', calculateHeight);
    }, []);

    return tableHeight;
};

// ========================================
// Icon Components
// ========================================

const DownloadIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
    </svg>
);

const ListIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
    </svg>
);

const FilterIcon = ({ className = "text-slate-400 hover:text-slate-600" }) => (
    <svg xmlns="http://www.w3.org/2000/svg" className={`h-4 w-4 cursor-pointer transition-colors ${className}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
    </svg>
);

const FilterBadge = () => (
    <span className="absolute -top-1 -right-1 flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
        <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
    </span>
);

const SortIndicator = ({ direction }: { direction: 'asc' | 'desc' }) => (
    <svg className="h-4 w-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={direction === 'asc' ? "M5 15l7-7 7 7" : "M19 9l-7 7-7-7"} />
    </svg>
);

const CheckIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" className={className} viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
    </svg>
);

// ========================================
// Filter Popup Component
// ========================================

interface FilterPopupProps {
    columnKey: string;
    currentFilter: { operator: string | null; value: string };
    onApply: (key: string, filter: { operator: string; value: string }) => void;
    onClear: (key: string) => void;
    onSort: (key: string, direction: 'asc' | 'desc') => void;
    onClose: () => void;
    sortConfig: { key: string; direction: 'asc' | 'desc' } | null;
}

const FilterPopup: React.FC<FilterPopupProps> = ({ columnKey, currentFilter, onApply, onClear, onSort, onClose, sortConfig }) => {
    const [operator, setOperator] = useState(currentFilter.operator || 'gt');
    const [value, setValue] = useState(currentFilter.value || '');
    const popupRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (popupRef.current && !popupRef.current.contains(event.target as Node)) {
                onClose();
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [onClose]);

    const handleApply = () => {
        if (value !== '') {
            onApply(columnKey, { operator, value });
        }
        onClose();
    };

    const handleClear = () => {
        onClear(columnKey);
        onClose();
    };

    const handleSort = (direction: 'asc' | 'desc') => {
        onSort(columnKey, direction);
        onClose();
    };

    const isSortedAsc = sortConfig?.key === columnKey && sortConfig.direction === 'asc';
    const isSortedDesc = sortConfig?.key === columnKey && sortConfig.direction === 'desc';

    const operators = [
        { value: 'gt', label: 'Greater than' },
        { value: 'gte', label: 'Greater than or equal to' },
        { value: 'lt', label: 'Less than' },
        { value: 'lte', label: 'Less than or equal to' },
        { value: 'eq', label: 'Equals' },
    ];

    return (
        <div ref={popupRef} className="absolute top-full mt-2 w-60 bg-white p-3 rounded-lg shadow-xl z-20 border border-slate-200 right-0 origin-top-right">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Sort</p>
            <div className="space-y-1">
                <button
                    onClick={() => handleSort('asc')}
                    className={`w-full text-left text-sm px-2 py-1.5 rounded hover:bg-slate-100 flex items-center justify-between transition-colors ${isSortedAsc ? 'bg-primary-light/50 text-primary-dark font-semibold' : 'text-slate-700'}`}
                >
                    <span>Sort Ascending</span>
                    {isSortedAsc && <CheckIcon className="h-4 w-4 text-primary" />}
                </button>
                <button
                    onClick={() => handleSort('desc')}
                    className={`w-full text-left text-sm px-2 py-1.5 rounded hover:bg-slate-100 flex items-center justify-between transition-colors ${isSortedDesc ? 'bg-primary-light/50 text-primary-dark font-semibold' : 'text-slate-700'}`}
                >
                    <span>Sort Descending</span>
                    {isSortedDesc && <CheckIcon className="h-4 w-4 text-primary" />}
                </button>
            </div>
            <hr className="my-3 border-slate-200" />
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Filter by Value</p>
            <div className="space-y-2">
                <select value={operator} onChange={e => setOperator(e.target.value)} className="w-full text-sm p-1.5 border border-slate-300 rounded-md bg-white focus:ring-1 focus:ring-primary focus:border-primary">
                    {operators.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
                </select>
                <input
                    type="number"
                    value={value}
                    onChange={e => setValue(e.target.value)}
                    className="w-full text-sm p-1.5 border border-slate-300 rounded-md focus:ring-1 focus:ring-primary focus:border-primary"
                    placeholder="Enter value..."
                    onKeyDown={(e) => e.key === 'Enter' && handleApply()}
                />
            </div>
            <hr className="my-3 border-slate-200" />
            <div className="flex justify-between items-center">
                <button onClick={handleClear} className="px-4 py-1.5 text-sm font-semibold bg-slate-200 text-slate-700 rounded-md hover:bg-slate-300 transition-colors">Clear</button>
                <button onClick={handleApply} className="px-4 py-1.5 text-sm font-semibold bg-primary text-white rounded-md hover:bg-primary-dark transition-colors">Apply</button>
            </div>
        </div>
    );
};

// ========================================
// Main Component
// ========================================

const WorkbenchDetailDEGMatrix: React.FC<WorkbenchDetailDEGMatrixProps> = ({
    workbenchId,
    comparisonName,
    toolName,
    selectedGenes,
    onSelectionChange,
    onAnalysisRequest,
    showComingSoon
}) => {
    const [searchTerm, setSearchTerm] = useState('');
    const [isActionMenuOpen, setActionMenuOpen] = useState(false);
    const actionMenuRef = useRef<HTMLDivElement>(null);
    const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' } | null>(null);
    const [filters, setFilters] = useState<{ [key: string]: { operator: string | null; value: string } }>({});
    const [activeFilter, setActiveFilter] = useState<string | null>(null);
    const [isGeneListOpen, setGeneListOpen] = useState(false);
    const geneListRef = useRef<HTMLDivElement>(null);
    const tableHeight = useTableHeight();

    // API 데이터 상태
    const [degData, setDegData] = useState<any[]>([]);
    const [columns, setColumns] = useState<string[]>([]);
    const [totalCount, setTotalCount] = useState(0);
    const [isLoading, setIsLoading] = useState(true);
    const [currentPage, setCurrentPage] = useState(1);
    const [selectAllState, setSelectAllState] = useState<0 | 1 | 2>(0);
    const limit = 1000;

    // API 데이터 fetch
    useEffect(() => {
        setSelectAllState(0);
        const fetchDEGData = async () => {
            try {
                setIsLoading(true);
                const response = await apiService.fetchDEGResults(workbenchId, comparisonName, {
                    tool_name: toolName,
                    page: currentPage,
                    limit: limit,
                    search: searchTerm || undefined,
                    data_type: 'matrix'
                });

                setDegData(response.data);
                setColumns(response.columns);
                setTotalCount(response.total);
            } catch (error) {
                console.error('Failed to fetch DEG data:', error);
                setDegData([]);
                setColumns([]);
                setTotalCount(0);
            } finally {
                setIsLoading(false);
            }
        };

        fetchDEGData();
    }, [workbenchId, comparisonName, toolName, currentPage, searchTerm]);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (actionMenuRef.current && !actionMenuRef.current.contains(event.target as Node)) {
                setActionMenuOpen(false);
            }
            if (geneListRef.current && !geneListRef.current.contains(event.target as Node)) {
                setGeneListOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const handleSort = (key: string, direction: 'asc' | 'desc') => {
        setSortConfig({ key, direction });
    };

    const handleApplyFilter = (key: string, filter: { operator: string; value: string }) => {
        setFilters(prev => ({ ...prev, [key]: filter }));
    };

    const handleClearFilter = (key: string) => {
        setFilters(prev => ({ ...prev, [key]: { operator: null, value: '' } }));
        if (sortConfig && sortConfig.key === key) {
            setSortConfig(null);
        }
    };

    const processedData = useMemo(() => {
        let data = [...degData];

        // 사용자 정의 필터 적용
        data = data.filter(row => {
            return Object.entries(filters).every(([key, filter]) => {
                if (!filter.operator || filter.value === '') return true;
                const rowValue = parseFloat(row[key]);
                const filterValue = parseFloat(filter.value);
                if (isNaN(rowValue) || isNaN(filterValue)) return true;

                switch (filter.operator) {
                    case 'gt': return rowValue > filterValue;
                    case 'gte': return rowValue >= filterValue;
                    case 'lt': return rowValue < filterValue;
                    case 'lte': return rowValue <= filterValue;
                    case 'eq': return rowValue === filterValue;
                    default: return true;
                }
            });
        });

        // 정렬 적용
        if (sortConfig) {
            data.sort((a, b) => {
                const aVal = parseFloat(a[sortConfig.key]);
                const bVal = parseFloat(b[sortConfig.key]);

                if (isNaN(aVal) || isNaN(bVal)) return 0;

                if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
                if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
                return 0;
            });
        }

        return data;
    }, [degData, filters, sortConfig]);

    // Fetch all gene IDs across all pages
    const fetchAllGeneIds = useCallback(async (): Promise<string[]> => {
        const params = new URLSearchParams({
            tool_name: toolName,
            page: '1',
            limit: totalCount.toString(),
            data_type: 'matrix'
        });
        if (searchTerm) params.append('search', searchTerm);
        try {
            const response = await fetch(
                `/api/workbenches/${workbenchId}/deg/results/${comparisonName}?${params}`,
                { credentials: 'include' }
            );
            if (response.ok) {
                const data = await response.json();
                const keyName = columns[0];
                return (data.data || []).map((g: any) => g[keyName] as string);
            }
        } catch (error) {
            console.error('Failed to fetch all gene IDs:', error);
        }
        return [];
    }, [workbenchId, comparisonName, toolName, totalCount, searchTerm, columns]);

    // 3-state Select All cycle handler
    const handleSelectAllCycle = useCallback(async () => {
        const firstColumnKey = columns[0];
        if (selectAllState === 0) {
            // State 0 → 1: Select current page
            const newSelected = new Set(selectedGenes);
            processedData.forEach(item => newSelected.add(item[firstColumnKey] as string));
            onSelectionChange(newSelected);
            setSelectAllState(1);
        } else if (selectAllState === 1) {
            // State 1 → 2: Select all pages via API
            setIsLoading(true);
            const allIds = await fetchAllGeneIds();
            onSelectionChange(new Set<string>(allIds));
            setSelectAllState(2);
            setIsLoading(false);
        } else {
            // State 2 → 0: Deselect all
            onSelectionChange(new Set());
            setSelectAllState(0);
        }
    }, [selectAllState, processedData, selectedGenes, onSelectionChange, fetchAllGeneIds, columns]);

    const handleSelectOne = (gene: string) => {
        const newSelectedGenes = new Set(selectedGenes);
        if (newSelectedGenes.has(gene)) newSelectedGenes.delete(gene);
        else newSelectedGenes.add(gene);
        onSelectionChange(newSelectedGenes);
        setSelectAllState(0);
    };

    const renderValue = (key: string, value: any) => {
        if (typeof value === 'number' && (key.toLowerCase().includes('logfc') || key.toLowerCase().includes('logcpm'))) {
            return value.toFixed(2);
        }
        if (typeof value === 'number' && (key.toLowerCase().includes('pvalue') || key.toLowerCase().includes('fdr'))) {
            return value.toExponential(2);
        }
        return value;
    };

    const isNumericColumn = (key: string) => {
        return key.toLowerCase().includes('logfc') ||
               key.toLowerCase().includes('logcpm') ||
               key.toLowerCase().includes('pvalue') ||
               key.toLowerCase().includes('fdr');
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-96">
                <div className="text-center">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 mb-4">
                        <svg className="animate-spin h-8 w-8 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                    </div>
                    <p className="text-sm text-slate-600">Loading DEG data...</p>
                </div>
            </div>
        );
    }

    const firstColumnKey = columns[0];

    return (
        <div className="h-full">
            <div className="flex justify-between items-center mb-4">
                <div className="flex items-center space-x-4">
                    <div className="relative">
                        <textarea
                            placeholder="Search Gene IDs (space, tab, or newline separated)..."
                            value={searchTerm}
                            onChange={e => setSearchTerm(e.target.value)}
                            className="pl-10 pr-4 py-2 border border-slate-300 rounded-lg focus:ring-primary focus:border-primary w-64 h-10 resize-none overflow-hidden"
                            rows={1}
                        />
                        <div className="absolute top-2.5 left-0 pl-3 flex items-center pointer-events-none">
                            <svg className="h-5 w-5 text-slate-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                            </svg>
                        </div>
                    </div>
                    <div className="relative" ref={geneListRef}>
                        <button
                            onClick={() => setGeneListOpen(!isGeneListOpen)}
                            className="px-4 py-2 text-sm font-semibold bg-white border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 flex items-center transition-colors"
                        >
                            <ListIcon />
                            <span className="ml-2">Load Gene List</span>
                        </button>
                        {isGeneListOpen && (
                            <div className="absolute top-full mt-2 w-56 bg-white rounded-md shadow-lg z-10 border max-h-60 overflow-y-auto">
                                <ul className="py-1">
                                    {GENE_SETS.map(setName => (
                                        <li key={setName}>
                                            <a
                                                href="#"
                                                onClick={(e) => {
                                                    e.preventDefault();
                                                    setGeneListOpen(false);
                                                    showComingSoon();
                                                }}
                                                className="block px-4 py-2 text-sm text-slate-700 hover:bg-slate-100 capitalize"
                                            >
                                                {setName.replace(/_/g, ' ')}
                                            </a>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </div>
                    <SelectableGeneTableShell
                        selectedGenes={Array.from(selectedGenes)}
                        onHeatmap={() => onAnalysisRequest('heatmap')}
                        heatmapLabel="Create Heatmap"
                        extraMenuItems={
                            <button
                                type="button"
                                onClick={showComingSoon}
                                className="block w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-100"
                            >
                                GO Analysis
                            </button>
                        }
                        analyzeButtonClassName="px-4 py-2 text-sm font-semibold bg-primary text-white rounded-lg hover:bg-primary-dark disabled:bg-slate-300 disabled:cursor-not-allowed flex items-center"
                        toolbarClassName="contents"
                        leftGroupClassName="contents"
                        rightGroupClassName="contents"
                    />
                </div>
                <div className="flex space-x-2">
                    <button onClick={showComingSoon} className="px-4 py-2 text-sm font-semibold bg-white border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 flex items-center transition-colors">
                        <DownloadIcon />
                        <span className="ml-2">Download Table</span>
                    </button>
                </div>
            </div>

            <p className="text-sm text-slate-500 mb-4">
                Comparison: {comparisonName.replace(/_/g, ' ')}.
                Showing {processedData.length} of {totalCount} genes.
                Tool: {toolName}
            </p>

            <div className="adaptive-height-table scrollable-table" style={{ height: tableHeight }}>
                <table className="data-table whitespace-nowrap">
                    <thead className="sticky-header">
                        <tr>
                            <th className="p-4 w-12">
                                <button
                                    onClick={handleSelectAllCycle}
                                    className="flex items-center justify-center w-5 h-5 hover:opacity-75 transition-opacity"
                                    title={
                                        selectAllState === 0 ? 'Select current page' :
                                        selectAllState === 1 ? 'Select all pages' :
                                        'Deselect all'
                                    }
                                >
                                    <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none" xmlns="http://www.w3.org/2000/svg">
                                        {selectAllState === 0 && (
                                            <rect x="1" y="1" width="14" height="14" rx="2" stroke="#9CA3AF" strokeWidth="1.5"/>
                                        )}
                                        {selectAllState === 1 && (
                                            <>
                                                <rect x="1" y="1" width="14" height="14" rx="2" stroke="#3B82F6" strokeWidth="1.5"/>
                                                <path d="M4 8.5l2.5 2.5 5-5.5" stroke="#3B82F6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                            </>
                                        )}
                                        {selectAllState === 2 && (
                                            <>
                                                <rect x="1" y="1" width="14" height="14" rx="2" fill="#1D4ED8" stroke="#1D4ED8" strokeWidth="1.5"/>
                                                <path d="M4 8.5l2.5 2.5 5-5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                            </>
                                        )}
                                    </svg>
                                </button>
                            </th>
                            {columns.map((header) => {
                                const isFilterable = isNumericColumn(header);
                                const isSorted = sortConfig && sortConfig.key === header;
                                const isFiltered = filters[header] && filters[header].operator && filters[header].value !== '';

                                return (
                                    <th key={header} className="px-4 py-3 text-left text-xs font-bold text-slate-600 uppercase tracking-wider">
                                        <div className="flex items-center gap-2">
                                            <div className="flex items-center">
                                                <span>{header.replace(/_/g, ' ')}</span>
                                                {isSorted && <SortIndicator direction={sortConfig.direction} />}
                                            </div>
                                            {isFilterable ? (
                                                <div className="relative">
                                                    <button onClick={() => setActiveFilter(activeFilter === header ? null : header)} className="relative">
                                                        <FilterIcon className={isFiltered || isSorted ? 'text-primary' : 'text-slate-400 hover:text-slate-600'} />
                                                        {isFiltered && !isSorted && <FilterBadge />}
                                                    </button>
                                                    {activeFilter === header && (
                                                        <FilterPopup
                                                            columnKey={header}
                                                            currentFilter={filters[header] || { operator: null, value: '' }}
                                                            onApply={handleApplyFilter}
                                                            onClear={handleClearFilter}
                                                            onSort={handleSort}
                                                            sortConfig={sortConfig}
                                                            onClose={() => setActiveFilter(null)}
                                                        />
                                                    )}
                                                </div>
                                            ) : <div className="w-4"></div>}
                                        </div>
                                    </th>
                                )
                            })}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                        {processedData.map((row, idx) => (
                            <tr key={idx} className="table-row">
                                <td className="p-4">
                                    <input
                                        type="checkbox"
                                        className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary"
                                        checked={selectedGenes.has(row[firstColumnKey] as string)}
                                        onChange={() => handleSelectOne(row[firstColumnKey] as string)}
                                    />
                                </td>
                                {columns.map(key => {
                                    const value = row[key];
                                    let cellClass = "px-4 py-3 text-sm text-slate-600 font-mono";
                                    if (key.toLowerCase().includes('logfc') && typeof value === 'number') {
                                        if (value > 1) cellClass += ' text-red-600 font-bold';
                                        if (value < -1) cellClass += ' text-blue-600 font-bold';
                                    }
                                    if (key === firstColumnKey) cellClass = "px-4 py-3 text-sm text-slate-800 font-semibold font-sans";
                                    return <td key={key} className={cellClass}>{renderValue(key, value)}</td>
                                })}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default WorkbenchDetailDEGMatrix;
