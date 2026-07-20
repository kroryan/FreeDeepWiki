export interface SavedApiCredentials {
  api_key?: string;
  api_endpoint?: string;
}

/**
 * Reads provider API key/endpoint overrides saved by UserSelector from
 * localStorage. Shared by anything that makes its own LLM call outside the
 * main wiki-generation flow (Ask chat, AI-assisted page edit, ...) so this
 * lookup isn't reimplemented per component.
 */
export const getSavedApiCredentials = (provider: string): SavedApiCredentials => {
  if (typeof window === 'undefined' || !provider) return {};
  const result: SavedApiCredentials = {};
  try {
    const savedKeys = localStorage.getItem('deepwiki_api_keys');
    if (savedKeys) {
      const parsedKeys = JSON.parse(savedKeys);
      if (parsedKeys[provider]) {
        result.api_key = parsedKeys[provider];
      }
    }
    const savedEndpoints = localStorage.getItem('deepwiki_api_endpoints');
    if (savedEndpoints) {
      const parsedEndpoints = JSON.parse(savedEndpoints);
      if (parsedEndpoints[provider]) {
        result.api_endpoint = parsedEndpoints[provider];
      }
    }
  } catch (e) {
    console.error('Failed to parse saved api settings in getSavedApiCredentials', e);
  }
  return result;
};
