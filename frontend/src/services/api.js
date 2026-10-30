const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()

export const API_BASE_URL = configuredApiBaseUrl
  ? configuredApiBaseUrl.replace(/\/$/, '')
  : import.meta.env.DEV
    ? 'http://localhost:8000'
    : ''

/**
 * Makes a request to the configured backend. Production deployments must set
 * VITE_API_BASE_URL to the Render service URL at build time.
 */
export async function apiRequest(path, options = {}) {
  if (!API_BASE_URL) {
    throw new Error('VITE_API_BASE_URL must be set for production builds.')
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }

  return response.status === 204 ? null : response.json()
}
