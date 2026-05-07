import React, { useState } from 'react';
import SettingsSidebar from '../components/settings/SettingsSidebar';
import ProfileSettings from '../components/settings/ProfileSettings';
import AIAnalysisSettings from '../components/settings/AIAnalysisSettings';
import DavidSettings from '../components/settings/DavidSettings';
import ReferenceSettings from '../components/settings/ReferenceSettings';
import HeatmapSettings from '../components/settings/HeatmapSettings';

interface SettingsProps {
    showComingSoon: () => void;
}

export default function Settings({ showComingSoon }: SettingsProps): React.ReactNode {
  const [activeMenu, setActiveMenu] = useState<string>('profile');

  const handleMenuSelect = (menuId: string) => {
    setActiveMenu(menuId);
  };

  const renderSettingsContent = () => {
    switch (activeMenu) {
      case 'profile':
        return <ProfileSettings showComingSoon={showComingSoon} />;

      case 'reference':
        return <ReferenceSettings showComingSoon={showComingSoon} />;

      case 'ai-analysis':
        return <AIAnalysisSettings />;

      case 'david':
        return <DavidSettings />;

      case 'heatmap':
        return <HeatmapSettings />;

      default:
        return <ProfileSettings showComingSoon={showComingSoon} />;
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-gray-200">
        <h2 className="text-2xl font-bold text-slate-800">Settings</h2>
        <p className="text-slate-500 mt-1">
          Application settings, profile management, and system integrations.
        </p>
      </div>

      {/* Main Content */}
      <div className="flex min-h-[600px]">
        {/* Sidebar */}
        <SettingsSidebar
          activeMenu={activeMenu}
          onMenuSelect={handleMenuSelect}
        />

        {/* Content Area */}
        <div className="flex-1 p-6">
          {renderSettingsContent()}
        </div>
      </div>
    </div>
  );
}
