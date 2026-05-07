import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

// ============================================================================
// Type Definitions
// ============================================================================

export interface HeatmapColors {
  high: string;
  middle: string;
  low: string;
}

export interface UserSettings {
  heatmap: {
    colors: HeatmapColors;
  };
  go: {
    davidEmail: string;
  };
  // Future settings can be added here:
  // theme?: 'light' | 'dark';
  // language?: 'en' | 'ko';
  // notifications?: boolean;
}

interface UserSettingsContextType {
  settings: UserSettings;
  updateSettings: (updates: Partial<UserSettings>) => Promise<void>;
  isLoading: boolean;
  isSaving: boolean;
  reloadSettings: () => Promise<void>;
}

// ============================================================================
// Default Values
// ============================================================================

const defaultSettings: UserSettings = {
  heatmap: {
    colors: {
      high: '#D32F2F',    // Red
      middle: '#FFFFFF',  // White
      low: '#1976D2'      // Blue
    }
  },
  go: {
    davidEmail: ''
  }
};

// ============================================================================
// Context
// ============================================================================

const UserSettingsContext = createContext<UserSettingsContextType | undefined>(undefined);

// ============================================================================
// Provider Component
// ============================================================================

interface UserSettingsProviderProps {
  children: ReactNode;
}

export const UserSettingsProvider: React.FC<UserSettingsProviderProps> = ({ children }) => {
  const [settings, setSettings] = useState<UserSettings>(defaultSettings);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Load settings on mount
  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setIsLoading(true);
    try {
      // Batch query for all settings
      const keys = ['heatmap.colors.high', 'heatmap.colors.middle', 'heatmap.colors.low', 'go.david.email'];
      const url = `/settings/value?key=${keys.join('&key=')}&` +
        `default_heatmap.colors.high=${encodeURIComponent(JSON.stringify(defaultSettings.heatmap.colors.high))}&` +
        `default_heatmap.colors.middle=${encodeURIComponent(JSON.stringify(defaultSettings.heatmap.colors.middle))}&` +
        `default_heatmap.colors.low=${encodeURIComponent(JSON.stringify(defaultSettings.heatmap.colors.low))}`;

      const response = await fetch(`/api${url}`, {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();

        if (data.values) {
          const loadedColors: HeatmapColors = {
            high: data.values['heatmap.colors.high']?.value || defaultSettings.heatmap.colors.high,
            middle: data.values['heatmap.colors.middle']?.value || defaultSettings.heatmap.colors.middle,
            low: data.values['heatmap.colors.low']?.value || defaultSettings.heatmap.colors.low
          };

          setSettings({
            heatmap: {
              colors: loadedColors
            },
            go: {
              davidEmail: data.values['go.david.email']?.value || defaultSettings.go.davidEmail
            }
          });
        } else {
          console.warn('[UserSettings] No data.values in response, using defaults');
          setSettings(defaultSettings);
        }
      } else {
        console.warn('[UserSettings] Failed to load settings, using defaults');
        setSettings(defaultSettings);
      }
    } catch (error) {
      console.error('[UserSettings] Failed to load settings:', error);
      setSettings(defaultSettings);
    } finally {
      setIsLoading(false);
    }
  };

  const updateSettings = async (updates: Partial<UserSettings>) => {
    setIsSaving(true);
    try {
      // Prepare values for batch update
      const values: Record<string, any> = {};

      // Handle heatmap colors update
      if (updates.heatmap?.colors) {
        values['heatmap.colors.high'] = updates.heatmap.colors.high;
        values['heatmap.colors.middle'] = updates.heatmap.colors.middle;
        values['heatmap.colors.low'] = updates.heatmap.colors.low;
      }

      if (typeof updates.go?.davidEmail !== 'undefined') {
        values['go.david.email'] = updates.go.davidEmail;
      }

      // Future: Add more setting types here as needed

      // Batch update to backend
      const response = await fetch('/api/settings/value', {
        method: 'PUT',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ values })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to save settings');
      }

      // Update local state after successful save
      setSettings(prev => ({
        ...prev,
        ...updates
      }));

      console.log('[UserSettings] Settings saved successfully');
    } catch (error) {
      console.error('[UserSettings] Failed to save settings:', error);
      throw error;
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <UserSettingsContext.Provider
      value={{
        settings,
        updateSettings,
        isLoading,
        isSaving,
        reloadSettings: loadSettings
      }}
    >
      {children}
    </UserSettingsContext.Provider>
  );
};

// ============================================================================
// Hooks
// ============================================================================

export const useUserSettings = () => {
  const context = useContext(UserSettingsContext);
  if (!context) {
    throw new Error('useUserSettings must be used within UserSettingsProvider');
  }
  return context;
};

// Convenience hook for heatmap colors (backward compatibility)
export const useHeatmapColors = () => {
  const { settings, updateSettings, isSaving, isLoading } = useUserSettings();

  return {
    colors: settings.heatmap.colors,
    setColors: (colors: HeatmapColors) => {
      // Update local state only (for preview without saving)
      // This is handled by component local state in HeatmapSettings
    },
    saveColors: async (colorsToSave?: HeatmapColors) => {
      const colors = colorsToSave || settings.heatmap.colors;
      await updateSettings({
        heatmap: {
          colors
        }
      });
    },
    loadColors: async () => {
      // Reload all settings (not just colors)
      // This is handled by reloadSettings in the provider
    },
    isLoading,
    isSaving
  };
};
