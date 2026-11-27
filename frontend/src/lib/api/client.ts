/**
 * Typed API Client for Order-to-Audit Factory Console
 * Features:
 *  - In-memory JWT access token storage with persistent storage backup
 *  - 401 Interceptor: attempts once to refresh or re-read session before redirecting
 *  - In-flight duplicate cancellation on session expiry
 *  - Clear session expiration messages and return-path routing
 */

export interface UserProfile {
  id: number;
  email: string;
  full_name: string;
  role: 'OWNER' | 'ADMIN' | 'SALESMAN' | 'PRODUCTION' | 'ACCOUNTANT';
  is_active: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  refresh_token?: string;
  user: UserProfile;
}

// In-Memory Token Store & Storage sync
let inMemoryToken: string | null = null;
let inMemoryRefreshToken: string | null = null;
let onUnauthorizedHandler: ((info?: { expired?: boolean; returnUrl?: string }) => void) | null = null;
let refreshPromise: Promise<boolean> | null = null;

const activeAbortControllers = new Set<AbortController>();

export function setAccessToken(token: string | null): void {
  inMemoryToken = token;
  try {
    if (typeof window !== 'undefined') {
      if (token) {
        sessionStorage.setItem('access_token', token);
        localStorage.setItem('access_token', token);
      } else {
        sessionStorage.removeItem('access_token');
        localStorage.removeItem('access_token');
      }
    }
  } catch {
    // Storage unavailable
  }
}

export function getAccessToken(): string | null {
  if (inMemoryToken) return inMemoryToken;
  try {
    if (typeof window !== 'undefined') {
      const stored = sessionStorage.getItem('access_token') || localStorage.getItem('access_token');
      if (stored) {
        inMemoryToken = stored;
        return stored;
      }
    }
  } catch {
    // Storage unavailable
  }
  return null;
}

export function setRefreshToken(token: string | null): void {
  inMemoryRefreshToken = token;
  try {
    if (typeof window !== 'undefined') {
      if (token) {
        sessionStorage.setItem('refresh_token', token);
        localStorage.setItem('refresh_token', token);
      } else {
        sessionStorage.removeItem('refresh_token');
        localStorage.removeItem('refresh_token');
      }
    }
  } catch {
    // Storage unavailable
  }
}

export function getRefreshToken(): string | null {
  if (inMemoryRefreshToken) return inMemoryRefreshToken;
  try {
    if (typeof window !== 'undefined') {
      const stored = sessionStorage.getItem('refresh_token') || localStorage.getItem('refresh_token');
      if (stored) {
        inMemoryRefreshToken = stored;
        return stored;
      }
    }
  } catch {
    // Storage unavailable
  }
  return null;
}

export function cancelInFlightRequests(): void {
  activeAbortControllers.forEach((controller) => {
    try {
      controller.abort('Session expired or cancelled');
    } catch {
      // Ignore abort errors
    }
  });
  activeAbortControllers.clear();
}

export function setOnUnauthorized(handler: (info?: { expired?: boolean; returnUrl?: string }) => void): void {
  onUnauthorizedHandler = handler;
}

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(status: number, message: string, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function tryRefreshSession(): Promise<boolean> {
  const rToken = getRefreshToken();
  if (!rToken) return false;

  try {
    const res = await fetch('/api/v1/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: rToken }),
    });

    if (res.ok) {
      const data = await res.json();
      if (data.access_token) {
        setAccessToken(data.access_token);
        if (data.refresh_token) {
          setRefreshToken(data.refresh_token);
        }
        return true;
      }
    }
  } catch {
    // Refresh failed
  }
  return false;
}

export interface RequestOptions extends RequestInit {
  _isRetry?: boolean;
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  const token = getAccessToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const url = endpoint.startsWith('http') ? endpoint : `/api/v1${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

  const controller = new AbortController();
  activeAbortControllers.add(controller);

  // Combine caller signal with our controller signal if provided
  const callerSignal = options.signal;
  if (callerSignal) {
    callerSignal.addEventListener('abort', () => controller.abort());
  }

  try {
    const res = await fetch(url, { ...options, headers, signal: controller.signal });

    if (res.status === 401) {
      const isAuthEndpoint = endpoint.includes('/auth/login') || endpoint.includes('/auth/refresh');
      const isRetry = options._isRetry;

      if (!isAuthEndpoint && !isRetry) {
        // Try once to refresh or re-read the session before redirecting
        if (!refreshPromise) {
          refreshPromise = tryRefreshSession().finally(() => {
            refreshPromise = null;
          });
        }
        const refreshed = await refreshPromise;
        if (refreshed) {
          return await request<T>(endpoint, { ...options, _isRetry: true });
        }
      }

      // Session really expired or refresh failed
      cancelInFlightRequests();
      setAccessToken(null);
      setRefreshToken(null);

      const currentPath = typeof window !== 'undefined'
        ? window.location.pathname + window.location.search
        : '/';

      if (onUnauthorizedHandler) {
        onUnauthorizedHandler({ expired: true, returnUrl: currentPath });
      }
      throw new ApiError(401, 'Your session expired. Sign in again.');
    }

    if (!res.ok) {
      let errData: any;
      try {
        errData = await res.json();
      } catch {
        errData = { detail: res.statusText };
      }
      throw new ApiError(res.status, errData?.detail || `Request failed with status ${res.status}`, errData);
    }

    return (await res.json()) as T;
  } catch (err: any) {
    if (err instanceof ApiError) {
      throw err;
    }
    if (err?.name === 'AbortError') {
      throw new ApiError(0, 'Request aborted.');
    }
    throw new ApiError(0, err.message || 'Network connection failed. Backend might be offline.');
  } finally {
    activeAbortControllers.delete(controller);
  }
}

// Typed API Definitions
export const api = {
  auth: {
    login: async (email: string, password: string): Promise<LoginResponse> => {
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username: email, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Invalid credentials' }));
        throw new ApiError(res.status, err.detail || 'Login failed');
      }
      const data = await res.json();
      setAccessToken(data.access_token);
      if (data.refresh_token) {
        setRefreshToken(data.refresh_token);
      }
      return data;
    },
    me: async (): Promise<UserProfile> => {
      return request<UserProfile>('/auth/me');
    },
    logout: async (): Promise<void> => {
      cancelInFlightRequests();
      setAccessToken(null);
      setRefreshToken(null);
    },
  },
  dashboard: {
    getSummary: async (range: string = 'today'): Promise<any> => {
      return request<any>(`/dashboard/summary?range=${encodeURIComponent(range)}`);
    },
    getOrdersAwaitingApproval: async (): Promise<any[]> => {
      return request<any[]>('/orders?status=PENDING_APPROVAL');
    },
  },
};

export const apiClient = {
  get: <T>(endpoint: string, options?: RequestOptions): Promise<T> =>
    request<T>(endpoint, { method: 'GET', ...options }),
  post: <T>(endpoint: string, body?: any, options?: RequestOptions): Promise<T> =>
    request<T>(endpoint, { method: 'POST', body: body !== undefined ? JSON.stringify(body) : undefined, ...options }),
  put: <T>(endpoint: string, body?: any, options?: RequestOptions): Promise<T> =>
    request<T>(endpoint, { method: 'PUT', body: body !== undefined ? JSON.stringify(body) : undefined, ...options }),
  delete: <T>(endpoint: string, options?: RequestOptions): Promise<T> =>
    request<T>(endpoint, { method: 'DELETE', ...options }),
};
