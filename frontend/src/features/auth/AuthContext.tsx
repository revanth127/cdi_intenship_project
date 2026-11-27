import React, { createContext, useContext, useState, useEffect } from 'react';
import { api, getAccessToken, setAccessToken, setRefreshToken, setOnUnauthorized, UserProfile } from '@/lib/api/client';

interface AuthContextType {
  user: UserProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
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
    } finally {
      setIsLoading(false);
    }
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
