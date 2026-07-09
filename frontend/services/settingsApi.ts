/**
 * Settings API Service
 * Handles user settings with efficient single/batch operations
 */

const API_BASE_URL = '/api';

class SettingsAPIError extends Error {
  constructor(public status: number, message: string, public errorCode?: string) {
    super(message);
    this.name = 'SettingsAPIError';
  }
}

interface SettingValue {
  value: any;
  exists: boolean;
}

interface SingleValueResponse {
  status: 'success' | 'error';
  key: string;
  value: any;
  exists: boolean;
  error?: string;
}

interface MultiValueResponse {
  status: 'success' | 'error';
  values: Record<string, SettingValue>;
  error?: string;
}

interface SaveResponse {
  status: 'success' | 'error';
  message: string;
  key?: string;
  updated_keys?: string[];
  error?: string;
}

class SettingsAPI {
  private async fetchJSON<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;
    const config: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      credentials: 'include', // Include cookies for session management
      ...options,
    };

    try {
      const response = await fetch(url, config);
      const data = await response.json();

      if (!response.ok) {
        throw new SettingsAPIError(
          response.status,
          data.error || 'Request failed',
          data.error_code
        );
      }

      return data;
    } catch (error) {
      if (error instanceof SettingsAPIError) {
        throw error;
      }
      throw new SettingsAPIError(0, 'Network error occurred');
    }
  }

  /**
   * Get single setting value
   */
  async getValue(key: string, defaultValue?: any): Promise<any> {
    try {
      const result = await this.fetchJSON<SingleValueResponse>(`/settings/value?key=${encodeURIComponent(key)}`);
      return result.exists ? result.value : defaultValue;
    } catch (error) {
      console.warn(`Failed to get setting '${key}':`, error);
      return defaultValue;
    }
  }

  /**
   * Get multiple setting values in one request
   */
  async getValues(keys: string[], defaults: Record<string, any> = {}): Promise<Record<string, any>> {
    if (keys.length === 0) return {};

    try {
      // Join keys with & separator, then encode the entire string
      const keyString = keys.join('&');
      const keyParam = encodeURIComponent(keyString);
      const url = `/settings/value?key=${keyParam}`;
      console.log('[SETTINGS API] Requesting:', url);
      console.log('[SETTINGS API] Key string:', keyString);

      const result = await this.fetchJSON<MultiValueResponse>(url);
      console.log('[SETTINGS API] Raw response:', result);

      const values: Record<string, any> = {};
      for (const [key, data] of Object.entries(result.values)) {
        values[key] = data.exists ? data.value : defaults[key];
        console.log(`[SETTINGS API] Key ${key}: exists=${data.exists}, value=${JSON.stringify(data.value)}, final=${JSON.stringify(values[key])}`);
      }

      console.log('[SETTINGS API] Final processed values:', values);
      return values;
    } catch (error) {
      console.warn('[SETTINGS API] Failed to get multiple settings:', error);
      // Return defaults for all keys if request fails
      const fallbackValues: Record<string, any> = {};
      keys.forEach(key => {
        fallbackValues[key] = defaults[key];
      });
      console.log('[SETTINGS API] Using fallback values:', fallbackValues);
      return fallbackValues;
    }
  }

  /**
   * Set single setting value
   */
  async setValue(key: string, value: any): Promise<void> {
    await this.fetchJSON<SaveResponse>('/settings/value', {
      method: 'PUT',
      body: JSON.stringify({ key, value })
    });
  }

  /**
   * Set multiple setting values in one request
   */
  async setValues(values: Record<string, any>): Promise<void> {
    if (Object.keys(values).length === 0) return;

    await this.fetchJSON<SaveResponse>('/settings/value', {
      method: 'PUT',
      body: JSON.stringify({ values })
    });
  }

  /**
   * Check if setting exists
   */
  async hasValue(key: string): Promise<boolean> {
    try {
      const result = await this.fetchJSON<SingleValueResponse>(`/settings/value?key=${encodeURIComponent(key)}`);
      return result.exists;
    } catch (error) {
      return false;
    }
  }

  /**
   * Delete setting value
   */
  async deleteValue(key: string): Promise<void> {
    await this.fetchJSON<SaveResponse>(`/settings/value?key=${encodeURIComponent(key)}`, {
      method: 'DELETE'
    });
  }

  /**
   * Convenience method to get AI settings section
   */
  async getAISettings(): Promise<{
    provider?: string;
    model?: string;
    api_key_configured?: boolean;
    analysis_enabled?: boolean;
    features_enabled?: Record<string, boolean>;
  }> {
    const rawSettings = await this.getValues([
      'ai.provider',
      'ai.model',
      'ai.api_key_configured',
      'ai.analysis_enabled',
      'ai.features_enabled'
    ], {
      'ai.analysis_enabled': true, // Default to enabled
      'ai.features_enabled': {
        qc_analysis: true,
        deg_interpretation: true,
        pipeline_summary: false
      }
    });

    // Convert dot notation keys to simple keys
    return {
      provider: rawSettings['ai.provider'],
      model: rawSettings['ai.model'],
      api_key_configured: rawSettings['ai.api_key_configured'],
      analysis_enabled: rawSettings['ai.analysis_enabled'] !== false, // Convert null/undefined to true
      features_enabled: rawSettings['ai.features_enabled']
    };
  }

  /**
   * Convenience method to save AI settings section
   */
  async saveAISettings(settings: {
    provider: string;
    model: string;
    api_key?: string;
    analysis_enabled?: boolean;
    features_enabled?: Record<string, boolean>;
  }): Promise<void> {
    const values: Record<string, any> = {
      'ai.provider': settings.provider,
      'ai.model': settings.model
    };

    // Only update API key if explicitly provided (not undefined)
    if (settings.api_key !== undefined) {
      values['ai.api_key'] = settings.api_key;
      values['ai.api_key_configured'] = settings.api_key.length > 0;
    }

    // Always save analysis_enabled state (convert to boolean)
    if (settings.analysis_enabled !== undefined) {
      values['ai.analysis_enabled'] = Boolean(settings.analysis_enabled);
    }

    if (settings.features_enabled) {
      values['ai.features_enabled'] = settings.features_enabled;
    }

    await this.setValues(values);
  }

  async getGOSettings(): Promise<{
    david_email?: string;
  }> {
    const rawSettings = await this.getValues(['go.david.email'], {
      'go.david.email': ''
    });

    return {
      david_email: rawSettings['go.david.email'] || ''
    };
  }

  async saveGOSettings(settings: {
    david_email?: string;
  }): Promise<void> {
    const values: Record<string, any> = {};

    if (settings.david_email !== undefined) {
      values['go.david.email'] = settings.david_email.trim();
    }

    await this.setValues(values);
  }

  /**
   * Convenience method to get UI settings section
   */
  async getUISettings(): Promise<{
    theme?: string;
    language?: string;
    notifications_enabled?: boolean;
  }> {
    return await this.getValues([
      'ui.theme',
      'ui.language',
      'ui.notifications_enabled'
    ], {
      'ui.theme': 'light',
      'ui.language': 'en',
      'ui.notifications_enabled': true
    });
  }

  /**
   * Convenience method to save UI settings section
   */
  async saveUISettings(settings: {
    theme?: string;
    language?: string;
    notifications_enabled?: boolean;
  }): Promise<void> {
    const values: Record<string, any> = {};

    if (settings.theme !== undefined) {
      values['ui.theme'] = settings.theme;
    }
    if (settings.language !== undefined) {
      values['ui.language'] = settings.language;
    }
    if (settings.notifications_enabled !== undefined) {
      values['ui.notifications_enabled'] = settings.notifications_enabled;
    }

    if (Object.keys(values).length > 0) {
      await this.setValues(values);
    }
  }

  /**
   * Test AI connection with provided or current settings
   */
  async testAIConnection(testParams?: {
    provider?: string;
    model?: string;
    api_key?: string | null;
  }): Promise<{
    status: 'success' | 'error';
    message: string;
    provider?: string;
    model?: string;
    response_time?: number;
    error_type?: string;
  }> {
    const body = testParams ? {
      provider: testParams.provider,
      model: testParams.model,
      api_key: testParams.api_key
    } : undefined;

    return await this.fetchJSON<any>('/settings/ai/test-connection', {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined
    });
  }
}

// Export singleton instance
export const settingsAPI = new SettingsAPI();
export { SettingsAPIError };
export type { SettingValue, SingleValueResponse, MultiValueResponse, SaveResponse };
