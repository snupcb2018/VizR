
import React, { useState, useEffect } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import DashboardCard from '../components/DashboardCard';
import CreateWorkbenchModal from '../components/CreateWorkbenchModal';
import { Workbench, DashboardStats } from '../types';
import StatusBadge from '../components/StatusBadge';
import { apiService } from '../services/api';

interface DashboardProps {
    onSelectWorkbench: (workbench: Workbench) => void;
    showComingSoon: () => void;
}

export default function Dashboard({ onSelectWorkbench, showComingSoon }: DashboardProps): React.ReactNode {
  const [stats, setStats] = useState<DashboardStats>({
    total_workbenches: 0,
    active_workbenches: 0,
    completed_workbenches: 0,
    failed_workbenches: 0,
    pending_workbenches: 0
  });
  const [recentWorkbenches, setRecentWorkbenches] = useState<Workbench[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const fetchDashboardData = async () => {
    try {
      setIsLoading(true);

      const [statsResponse, recentResponse] = await Promise.all([
        apiService.getDashboardStats(),
        apiService.getRecentWorkbenches()
      ]);

      setStats(statsResponse.stats);
      setRecentWorkbenches(recentResponse.workbenches);
    } catch (error) {
      console.error('[Dashboard] Error fetching dashboard data:', error);
      setError('Failed to load dashboard data');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const handleWorkbenchCreated = async (workbenchId: number) => {
    setIsCreateModalOpen(false);

    // Fetch the newly created workbench details
    try {
      const response = await fetch(`/api/workbenches/${workbenchId}`, {
        credentials: 'include'
      });

      if (response.ok) {
        const data = await response.json();
        const newWorkbench: Workbench = data.workbench;

        // Navigate to the new workbench overview
        onSelectWorkbench(newWorkbench);
      } else {
        // Fallback: just refresh dashboard if we can't fetch the workbench
        fetchDashboardData();
      }
    } catch (error) {
      console.error('[Dashboard] Error fetching new workbench:', error);
      // Fallback: just refresh dashboard
      fetchDashboardData();
    }
  };

  const statusDistribution = [
    { name: 'Running', value: stats.active_workbenches, color: '#06b6d4' },
    { name: 'Completed', value: stats.completed_workbenches, color: '#10b981' },
    { name: 'Failed', value: stats.failed_workbenches, color: '#f43f5e' },
    { name: 'Pending', value: stats.pending_workbenches, color: '#f59e0b' }
  ].filter(item => item.value > 0); // Only show non-zero values

  if (isLoading) {
    return (
      <div className="space-y-8">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Dashboard Overview</h2>
          <p className="text-slate-500 mt-1">Loading your recent analysis activity...</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="bg-white p-6 rounded-2xl shadow-sm animate-pulse">
              <div className="h-4 bg-slate-200 rounded w-3/4 mb-2"></div>
              <div className="h-8 bg-slate-200 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-8">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Dashboard Overview</h2>
          <p className="text-red-500 mt-1">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <CreateWorkbenchModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        showComingSoon={showComingSoon}
        onWorkbenchCreated={handleWorkbenchCreated}
      />

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Dashboard Overview</h2>
          <p className="text-slate-500 mt-1">Here's a snapshot of your recent analysis activity.</p>
        </div>
        <button
          onClick={() => setIsCreateModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors"
        >
          <PlusIcon />
          Create Workbench
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <DashboardCard 
          title="Active Workbenches" 
          value={String(stats.active_workbenches)} 
          icon={<PlayIcon />} 
          color="bg-cyan-100 text-cyan-700" 
        />
        <DashboardCard 
          title="Analysis Completed" 
          value={String(stats.completed_workbenches)} 
          icon={<CheckCircleIcon />} 
          color="bg-emerald-100 text-emerald-700" 
        />
        <DashboardCard 
          title="Analysis Failed" 
          value={String(stats.failed_workbenches)} 
          icon={<XCircleIcon />} 
          color="bg-rose-100 text-rose-700" 
        />
        <DashboardCard 
          title="Total Workbenches" 
          value={String(stats.total_workbenches)} 
          icon={<CollectionIcon />} 
          color="bg-indigo-100 text-indigo-700" 
        />
      </div>
      
      {/* Content Sections */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3 bg-white p-6 rounded-2xl shadow-sm">
           <h3 className="font-semibold text-slate-800 mb-4">Recent Workbenches</h3>
           {recentWorkbenches.length === 0 ? (
             <div className="text-center py-8 text-slate-500">
               <CollectionIcon />
               <p className="mt-2">No workbenches yet</p>
               <p className="text-sm">Create your first workbench to get started</p>
             </div>
           ) : (
             <div className="overflow-x-auto">
               <table className="w-full text-sm text-left">
                  <thead className="text-xs text-slate-500 uppercase bg-slate-100 rounded-t-lg">
                    <tr>
                      <th className="p-3">Name</th>
                      <th className="p-3">Species</th>
                      <th className="p-3">Status</th>
                      <th className="p-3">Last Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentWorkbenches.map(wb => (
                       <tr key={wb.id} onClick={() => onSelectWorkbench(wb)} className="border-b border-slate-200 hover:bg-slate-50 cursor-pointer">
                          <td className="p-3 font-medium text-slate-700">{wb.name}</td>
                          <td className="p-3 text-slate-500 capitalize">{wb.species}</td>
                          <td className="p-3"><StatusBadge status={wb.status}/></td>
                          <td className="p-3 text-slate-500">{apiService.formatRelativeTime(wb.updated_at)}</td>
                       </tr>
                    ))}
                  </tbody>
               </table>
             </div>
           )}
        </div>
        <div className="lg:col-span-2 bg-white p-6 rounded-2xl shadow-sm">
            <h3 className="font-semibold text-slate-800 mb-4">Workbench Status</h3>
            {statusDistribution.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                <p>No data to display</p>
              </div>
            ) : (
              <div style={{ width: '100%', height: 200 }}>
                  <ResponsiveContainer>
                       <PieChart>
                           <Pie 
                             data={statusDistribution} 
                             dataKey="value" 
                             nameKey="name" 
                             cx="50%" 
                             cy="50%" 
                             outerRadius={80} 
                             label={({name, value}) => `${name}: ${value}`}
                           >
                              {statusDistribution.map((entry, index) => 
                                <Cell key={`cell-${index}`} fill={entry.color} />
                              )}
                           </Pie>
                           <Tooltip />
                       </PieChart>
                  </ResponsiveContainer>
              </div>
            )}
        </div>
      </div>
    </div>
  );
}

// Icons
const PlusIcon = () => <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>;
const PlayIcon = () => <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
const CheckCircleIcon = () => <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
const XCircleIcon = () => <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
const CollectionIcon = () => <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>;
