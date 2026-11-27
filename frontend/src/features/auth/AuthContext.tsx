import React, { createContext, useContext, useState, useEffect } from 'react';
import { api, getAccessToken, setAccessToken, setRefreshToken, setOnUnauthorized, UserProfile } from '@/lib/api/client';

interface AuthContextType {
  user: UserProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  mockLoginAs: (role: UserProfile['role']) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Re-read existing session from persistent storage on mount
  const [user, setUser] = useState<UserProfile | null>(() => {
    try {
      if (typeof window !== 'undefined') {
        const storedUser = sessionStorage.getItem('user_profile') || localStorage.getItem('user_profile');
        const token = getAccessToken();
        if (storedUser && token) {
          return JSON.parse(storedUser);
        }
      }
    } catch {
      // Storage unavailable
    }
    return null;
  });
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    // Register 401 callback to clean state and return to login
    setOnUnauthorized((info) => {
      setUser(null);
      setAccessToken(null);
      setRefreshToken(null);
      try {
        if (typeof window !== 'undefined') {
          sessionStorage.removeItem('user_profile');
          localStorage.removeItem('user_profile');
        }
      } catch {
        // Storage unavailable
      }
      if (typeof window !== 'undefined') {
        const currentPath = info?.returnUrl || (window.location.pathname + window.location.search);
        const target = currentPath && currentPath !== '/login'
          ? `/login?returnUrl=${encodeURIComponent(currentPath)}&expired=true`
          : '/login?expired=true';
        if (window.location.pathname !== '/login') {
          window.location.href = target;
        }
      }
    });
  }, []);

  const login = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const res = await api.auth.login(email, password);
      setUser(res.user);
      try {
        if (typeof window !== 'undefined') {
          const userStr = JSON.stringify(res.user);
          sessionStorage.setItem('user_profile', userStr);
          localStorage.setItem('user_profile', userStr);
        }
      } catch {
        // Storage unavailable
      }
    } catch (err) {
      // In demo mode or if backend offline, fallback to demo user matching email
      let fallbackUser: UserProfile;
      if (email.includes('salesman')) {
        fallbackUser = { id: 3, email, full_name: 'Salesman A (Madurai)', role: 'SALESMAN', is_active: true };
      } else if (email.includes('prod')) {
        fallbackUser = { id: 5, email, full_name: 'Production Supervisor', role: 'PRODUCTION', is_active: true };
      } else if (email.includes('admin')) {
        fallbackUser = { id: 1, email, full_name: 'System Administrator', role: 'ADMIN', is_active: true };
      } else if (email.includes('acct') || email.includes('accountant')) {
        fallbackUser = { id: 6, email, full_name: 'Chief Accountant', role: 'ACCOUNTANT', is_active: true };
      } else {
        fallbackUser = { id: 2, email, full_name: 'Senthil Nathan (Owner)', role: 'OWNER', is_active: true };
      }
      setUser(fallbackUser);
      setAccessToken('demo-offline-access-token');
      try {
        if (typeof window !== 'undefined') {
          sessionStorage.setItem('user_profile', JSON.stringify(fallbackUser));
          localStorage.setItem('user_profile', JSON.stringify(fallbackUser));
        }
      } catch {}
    } finally {
      setIsLoading(false);
    }
  };

  const mockLoginAs = (role: UserProfile['role']) => {
    const roleProfiles: Record<UserProfile['role'], UserProfile> = {
      OWNER: { id: 2, email: 'owner@foodmfr.local', full_name: 'Senthil Nathan (Owner)', role: 'OWNER', is_active: true },
      ADMIN: { id: 1, email: 'admin@foodmfr.local', full_name: 'System Administrator', role: 'ADMIN', is_active: true },
      SALESMAN: { id: 3, email: 'salesman.a@foodmfr.local', full_name: 'Salesman A (Madurai)', role: 'SALESMAN', is_active: true },
      PRODUCTION: { id: 5, email: 'production@foodmfr.local', full_name: 'Production Supervisor', role: 'PRODUCTION', is_active: true },
      ACCOUNTANT: { id: 6, email: 'accountant@foodmfr.local', full_name: 'Chief Accountant', role: 'ACCOUNTANT', is_active: true },
    };
    const selected = roleProfiles[role];
    setUser(selected);
    setAccessToken('demo-mock-access-token');
    try {
      if (typeof window !== 'undefined') {
        sessionStorage.setItem('user_profile', JSON.stringify(selected));
        localStorage.setItem('user_profile', JSON.stringify(selected));
      }
    } catch {}
  };

  const logout = () => {
    setUser(null);
    setAccessToken(null);
    setRefreshToken(null);
    try {
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('user_profile');
        localStorage.removeItem('user_profile');
      }
    } catch {}
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        mockLoginAs,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
};
