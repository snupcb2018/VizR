
import React, { useState, useEffect } from 'react';
import { Workbench } from '../types';
import WorkbenchListItem from '../components/WorkbenchListItem';
import CreateWorkbenchModal from '../components/CreateWorkbenchModal';
import MethodTextModal from '../components/MethodTextModal';

interface WorkbenchOverviewProps {
  onSelectWorkbench: (workbench: Workbench) => void;
  showComingSoon: () => void;
}

export default function WorkbenchOverview({ onSelectWorkbench, showComingSoon }: WorkbenchOverviewProps): React.ReactNode {
  const [isCreateModalOpen, setCreateModalOpen] = useState(false);
  const [workbenches, setWorkbenches] = useState<Workbench[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [methodModalWorkbench, setMethodModalWorkbench] = useState<Workbench | null>(null);

  // Fetch workbenches from API
  const fetchWorkbenches = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/workbenches/', {
        credentials: 'include'
      });

      if (!response.ok) {
        throw new Error('Failed to fetch workbenches');
      }

      const data = await response.json();
      setWorkbenches(data.workbenches || []);
      setError(null);
    } catch (err) {
      console.error('Error fetching workbenches:', err);
      setError('Failed to load workbenches');
      setWorkbenches([]);
    } finally {
      setLoading(false);
    }
  };

  // Load workbenches on component mount
  useEffect(() => {
    fetchWorkbenches();
  }, []);

  // Handle workbench creation
  const handleWorkbenchCreated = (workbenchId: number) => {
    // Refresh the list
    fetchWorkbenches();
    
    // Navigate to the new workbench detail
    // Find the workbench in the list and select it
    setTimeout(() => {
      const newWorkbench = workbenches.find(wb => wb.id === workbenchId);
      if (newWorkbench) {
        onSelectWorkbench(newWorkbench);
      } else {
        // If not found in current list, create a temporary workbench object
        const tempWorkbench: Workbench = {
          id: workbenchId,
          name: 'New Workbench',
          status: 'pending',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          species: '',
          rawFilesCount: 0,
          samplesCount: 0
        };
        onSelectWorkbench(tempWorkbench);
      }
    }, 500);
  };

  return (
    <div className="bg-white p-6 rounded-2xl shadow-sm">
        <CreateWorkbenchModal
          isOpen={isCreateModalOpen}
          onClose={() => setCreateModalOpen(false)}
          showComingSoon={showComingSoon}
          onWorkbenchCreated={handleWorkbenchCreated}
        />
        {methodModalWorkbench && (
          <MethodTextModal
            isOpen={!!methodModalWorkbench}
            onClose={() => setMethodModalWorkbench(null)}
            workbenchId={methodModalWorkbench.id}
            workbenchName={methodModalWorkbench.name}
          />
        )}
        <div className="flex justify-between items-center mb-6">
            <div>
                <h2 className="text-2xl font-bold text-slate-800">Workbench Overview</h2>
                <p className="text-slate-500 mt-1">Manage your projects and view their status.</p>
            </div>
            <button onClick={() => setCreateModalOpen(true)} className="flex items-center bg-primary text-white font-semibold px-4 py-2 rounded-lg hover:bg-primary-dark transition-colors">
                <PlusIcon />
                <span className="ml-2">Create Workbench</span>
            </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin w-8 h-8 border-4 border-primary border-t-transparent rounded-full"></div>
            <span className="ml-3 text-slate-600">Loading workbenches...</span>
          </div>
        ) : error ? (
          <div className="text-center py-12">
            <div className="text-red-500 mb-2">
              <svg className="w-12 h-12 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
            </div>
            <p className="text-slate-600 mb-4">{error}</p>
            <button 
              onClick={fetchWorkbenches}
              className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition-colors"
            >
              Try Again
            </button>
          </div>
        ) : workbenches.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-slate-400 mb-4">
              <svg className="w-16 h-16 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-slate-800 mb-2">No workbenches yet</h3>
            <p className="text-slate-600 mb-4">Get started by creating your first RNA-seq analysis workbench.</p>
            <button 
              onClick={() => setCreateModalOpen(true)}
              className="px-6 py-3 bg-primary text-white font-semibold rounded-lg hover:bg-primary-dark transition-colors"
            >
              Create Your First Workbench
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
                <thead className="text-xs text-slate-500 uppercase bg-slate-100 rounded-t-lg">
                    <tr>
                        <th className="p-4">Name</th>
                        <th className="p-4">Status</th>
                        <th className="p-4">Created At</th>
                        <th className="p-4">Last Updated</th>
                        <th className="p-4 text-center w-24">Method</th>
                    </tr>
                </thead>
                <tbody>
                    {workbenches.map(wb => (
                        <WorkbenchListItem
                          key={wb.id}
                          workbench={wb}
                          onSelect={onSelectWorkbench}
                          onMethodClick={wb.status === 'completed' ? () => setMethodModalWorkbench(wb) : undefined}
                        />
                    ))}
                </tbody>
            </table>
          </div>
        )}
    </div>
  );
}

const PlusIcon = () => <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>;
