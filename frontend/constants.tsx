
import { Workbench, WorkbenchStatus } from './types';

export const MOCK_WORKBENCHES: Workbench[] = [
  {
    id: 1,
    name: 'Arabidopsis thaliana Cold Stress Study',
    status: WorkbenchStatus.Running,
    createdAt: '2024-07-20',
    lastUpdated: '2 minutes ago',
  },
  {
    id: 2,
    name: 'Lemna gibba Nutrient Deprivation',
    status: WorkbenchStatus.Completed,
    createdAt: '2024-07-18',
    lastUpdated: '2 days ago',
  },
  {
    id: 3,
    name: 'Comparative Transcriptomics of Duckweed',
    status: WorkbenchStatus.Completed,
    createdAt: '2024-07-15',
    lastUpdated: '5 days ago',
  },
  {
    id: 4,
    name: 'Initial QC for Frog Development',
    status: WorkbenchStatus.Failed,
    createdAt: '2024-07-12',
    lastUpdated: '1 week ago',
  },
  {
    id: 5,
    name: 'A. thaliana root development - Pilot',
    status: WorkbenchStatus.Pending,
    createdAt: '2024-07-10',
    lastUpdated: '10 days ago',
  },
    {
    id: 6,
    name: 'Heat Shock Response in Lemna Minor',
    status: WorkbenchStatus.Completed,
    createdAt: '2024-06-25',
    lastUpdated: '3 weeks ago',
  },
];
