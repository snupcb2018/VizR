import React from 'react';
import { useAuth } from '../../contexts/AuthContext';

interface SettingsMenuItem {
  id: string;
  label: string;
  icon: string;
  badge?: string;
}

interface SettingsSidebarProps {
  activeMenu: string;
  onMenuSelect: (menuId: string) => void;
}

const ALL_SETTINGS_MENUS: SettingsMenuItem[] = [
  { id: 'profile', label: 'User Profile', icon: '👤' },
  { id: 'heatmap', label: 'Heatmap Colors', icon: '🎨' },
  { id: 'reference', label: 'Reference Genomes', icon: '🧬' },
  { id: 'ai-analysis', label: 'AI Analysis', icon: '🤖' },
  { id: 'david', label: 'DAVID', icon: '🧪' }
];

const SettingsSidebar: React.FC<SettingsSidebarProps> = ({ activeMenu, onMenuSelect }) => {
  const { user } = useAuth();
  const isAdmin = user?.username === 'admin';

  // Admin 계정은 User Profile만 표시
  const SETTINGS_MENUS = isAdmin
    ? ALL_SETTINGS_MENUS.filter(menu => menu.id === 'profile')
    : ALL_SETTINGS_MENUS;

  return (
    <div className="w-64 bg-white border-r border-gray-200 p-4">
      <nav className="space-y-2">
        {SETTINGS_MENUS.map((menu) => (
          <button
            key={menu.id}
            onClick={() => onMenuSelect(menu.id)}
            className={`w-full flex items-center justify-between px-3 py-2 text-left rounded-lg transition-colors ${
              activeMenu === menu.id
                ? 'bg-blue-50 text-blue-700 border border-blue-200'
                : 'text-gray-700 hover:bg-gray-50'
            }`}
          >
            <div className="flex items-center">
              <span className="text-xl mr-3">{menu.icon}</span>
              <span className="font-medium">{menu.label}</span>
            </div>

            {menu.badge && (
              <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded-full">
                {menu.badge}
              </span>
            )}
          </button>
        ))}
      </nav>
    </div>
  );
};

export default SettingsSidebar;
