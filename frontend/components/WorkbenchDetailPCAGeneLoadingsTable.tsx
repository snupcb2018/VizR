import React, { useState, useEffect, useMemo } from 'react';

interface LoadingsData {
  workbench_id: number;
  loadings: Record<string, Record<string, number>>;
  genes: string[];
  components: string[];
  total_genes: number;
  current_page: number;
  total_pages: number;
  page_size: number;
  status: string;
}

interface WorkbenchDetailPCAGeneLoadingsTableProps {
  workbenchId: number;
}

const WorkbenchDetailPCAGeneLoadingsTable: React.FC<WorkbenchDetailPCAGeneLoadingsTableProps> = ({ workbenchId }) => {
  const [loadingsData, setLoadingsData] = useState<LoadingsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [sortPC, setSortPC] = useState('PC1');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await fetch(
          `/api/workbenches/${workbenchId}/pca/loadings?page=${currentPage}&page_size=${pageSize}&pc=${sortPC}&sort_order=${sortOrder}`
        );

        if (!response.ok) throw new Error('Failed to fetch loadings data');
        const result = await response.json();

        if (result.status === 'not_available') {
          setError('PCA loadings not available. Please run PCA analysis first.');
          setIsLoading(false);
          return;
        }

        setLoadingsData(result);
        setIsLoading(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error occurred');
        setIsLoading(false);
      }
    };

    fetchData();
  }, [workbenchId, currentPage, pageSize, sortPC, sortOrder]);

  const topGenes = useMemo(() => {
    if (!loadingsData) return [];

    return loadingsData.genes.map(gene => {
      const loadings = loadingsData.loadings[gene];
      const pcValue = loadings[sortPC];
      const absValue = Math.abs(pcValue);

      return {
        gene,
        value: pcValue,
        absValue,
        loadings,
      };
    });
  }, [loadingsData, sortPC]);

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && loadingsData && newPage <= loadingsData.total_pages) {
      setCurrentPage(newPage);
    }
  };

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize);
    setCurrentPage(1);
  };

  const handleSortChange = (pc: string) => {
    if (sortPC === pc) {
      setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc');
    } else {
      setSortPC(pc);
      setSortOrder('desc');
    }
    setCurrentPage(1);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
        <div className="flex items-center">
          <svg className="w-6 h-6 text-yellow-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <h3 className="text-yellow-800 font-semibold">Data Not Available</h3>
            <p className="text-yellow-700 text-sm mt-1">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!loadingsData) {
    return null;
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-gray-700">Sort by PC:</label>
            <select
              value={sortPC}
              onChange={(e) => handleSortChange(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {loadingsData.components.map((pc) => (
                <option key={pc} value={pc}>{pc}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-gray-700">Sort order:</label>
            <select
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as 'asc' | 'desc')}
              className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="desc">Highest absolute value</option>
              <option value="asc">Lowest absolute value</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-gray-700">Genes per page:</label>
            <select
              value={pageSize}
              onChange={(e) => handlePageSizeChange(Number(e.target.value))}
              className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
              <option value="200">200</option>
            </select>
          </div>
          <div className="ml-auto text-sm text-gray-600">
            Total genes: {loadingsData.total_genes.toLocaleString()}
          </div>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-blue-900 mb-1">Gene Loadings</h3>
        <p className="text-sm text-blue-800">
          Gene loadings represent the contribution of each gene to each principal component.
          Higher absolute values indicate genes that contribute more strongly to the component.
        </p>
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider sticky left-0 bg-gray-50">
                  Gene ID
                </th>
                {loadingsData.components.slice(0, 5).map((pc) => (
                  <th
                    key={pc}
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                    onClick={() => handleSortChange(pc)}
                  >
                    <div className="flex items-center gap-1">
                      {pc}
                      {sortPC === pc && (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          {sortOrder === 'desc' ? (
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          ) : (
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                          )}
                        </svg>
                      )}
                    </div>
                  </th>
                ))}
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Abs({sortPC})
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {topGenes.map((item, idx) => (
                <tr key={item.gene} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 sticky left-0 bg-white">
                    {item.gene}
                  </td>
                  {loadingsData.components.slice(0, 5).map((pc) => {
                    const value = item.loadings[pc];
                    const isHighlight = pc === sortPC;
                    return (
                      <td
                        key={pc}
                        className={`px-6 py-4 whitespace-nowrap text-sm ${
                          isHighlight ? 'font-semibold text-gray-900' : 'text-gray-700'
                        }`}
                      >
                        {value.toFixed(6)}
                      </td>
                    );
                  })}
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-blue-600">
                    {item.absValue.toFixed(6)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-700">
            Showing page {loadingsData.current_page} of {loadingsData.total_pages}
            {' '}({((loadingsData.current_page - 1) * loadingsData.page_size) + 1}-
            {Math.min(loadingsData.current_page * loadingsData.page_size, loadingsData.total_genes)} of {loadingsData.total_genes.toLocaleString()} genes)
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handlePageChange(1)}
              disabled={currentPage === 1}
              className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              First
            </button>
            <button
              onClick={() => handlePageChange(currentPage - 1)}
              disabled={currentPage === 1}
              className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <button
              onClick={() => handlePageChange(currentPage + 1)}
              disabled={currentPage === loadingsData.total_pages}
              className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
            <button
              onClick={() => handlePageChange(loadingsData.total_pages)}
              disabled={currentPage === loadingsData.total_pages}
              className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Last
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default WorkbenchDetailPCAGeneLoadingsTable;
