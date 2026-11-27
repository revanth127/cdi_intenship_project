import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { apiClient } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Factory, Lock, Mail, ArrowRight, UserCheck } from 'lucide-react';

interface DemoRoleConfig {
  title: string;
  email: string;
  password: string;
  access: string;
}

const ROLE_HOME_PAGES: Record<string, string> = {
  SALESMAN: '/orders/new',
  ADMIN: '/orders',
  PRODUCTION: '/production',
  ACCOUNTANT: '/reports',
  OWNER: '/',
};

export const LoginPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const returnUrl = searchParams.get('returnUrl');
  const isExpired = searchParams.get('expired') === 'true';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [demoRoles, setDemoRoles] = useState<DemoRoleConfig[]>([]);
  const [demoCredentialsError, setDemoCredentialsError] = useState<string | null>(null);
  const { login, isLoading } = useAuth();
  const navigate = useNavigate();

  // Demo mode flag from env (visible only when VITE_DEMO_MODE=true)
  const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true';

  useEffect(() => {
    if (!isDemoMode) return;

    let active = true;
    apiClient.get<DemoRoleConfig[]>('/auth/demo-credentials')
      .then((credentials) => {
        if (active) setDemoRoles(credentials);
      })
      .catch((requestError: Error) => {
        if (active) setDemoCredentialsError(requestError.message);
      });

    return () => {
      active = false;
    };
  }, [isDemoMode]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await login(email, password);
      // Determine landing page based on authenticated user's role
      const stored = sessionStorage.getItem('user_profile') || localStorage.getItem('user_profile');
      let targetPath = '/';
      if (stored) {
        try {
          const userObj = JSON.parse(stored);
          targetPath = ROLE_HOME_PAGES[userObj.role] || '/';
        } catch {
          // fallback
        }
      }
      navigate(returnUrl && returnUrl !== '/' && returnUrl !== '/login' ? returnUrl : targetPath);
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    }
  };

  const handleSelectRole = (role: DemoRoleConfig) => {
    setEmail(role.email);
    setPassword(role.password);
  };

  return (
    <div className="min-h-screen bg-page flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Brand Header */}
        <div className="flex items-center gap-2 mb-6 justify-center">
          <div className="w-8 h-8 rounded-[6px] bg-accent flex items-center justify-center text-white">
            <Factory className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-text-primary tracking-tight">
              Order-to-Audit Console
            </h1>
            <p className="text-xs text-text-secondary">Sri Murugan Foods Operations</p>
          </div>
        </div>

        {/* Login Card */}
        <Card>
          <CardContent className="pt-6">
            <form onSubmit={handleSubmit} className="space-y-4">
              {isExpired && !error && (
                <div
                  className="p-2.5 rounded-[4px] bg-status-breach-bg border border-status-breach-border text-status-breach-text text-xs"
                  data-testid="session-expired-alert"
                >
                  Your session expired. Sign in again.
                </div>
              )}
              {error && (
                <div className="p-2.5 rounded-[4px] bg-status-breach-bg border border-status-breach-border text-status-breach-text text-xs">
                  {error}
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                  Email Address
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-text-muted absolute left-2.5 top-2.5" />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full h-9 pl-9 pr-3 rounded-[6px] border border-border bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent"
                    placeholder="user@foodmfr.local"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                  Password
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-text-muted absolute left-2.5 top-2.5" />
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full h-9 pl-9 pr-3 rounded-[6px] border border-border bg-white text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent"
                    placeholder="••••••••"
                  />
                </div>
              </div>

              <Button
                type="submit"
                variant="primary"
                size="md"
                className="w-full gap-2 mt-2"
                disabled={isLoading}
              >
                <span>{isLoading ? 'Signing in...' : 'Sign in'}</span>
                <ArrowRight className="w-4 h-4" />
              </Button>
            </form>

            {/* Test Logins Block (Visible only when VITE_DEMO_MODE=true) */}
            {isDemoMode && (
              <div className="mt-6 pt-5 border-t border-border" data-testid="demo-mode-section">
                <div className="flex items-center gap-1.5 mb-2.5">
                  <UserCheck className="w-3.5 h-3.5 text-text-muted" />
                  <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Demo Mode Logins
                  </span>
                </div>
                <div className="space-y-2">
                  {demoCredentialsError && (
                    <p className="text-xs text-status-breach-text" role="alert">
                      Could not load demo credentials: {demoCredentialsError}
                    </p>
                  )}
                  {!demoCredentialsError && demoRoles.length === 0 && (
                    <p className="text-xs text-text-muted">Loading demo credentials...</p>
                  )}
                  {demoRoles.map((r) => (
                    <button
                      key={r.title}
                      type="button"
                      onClick={() => handleSelectRole(r)}
                      data-testid={`demo-role-${r.title.toLowerCase()}`}
                      className="w-full p-2.5 text-left text-xs rounded-[4px] border border-border hover:bg-surface-subtle transition-colors flex flex-col justify-between"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-text-primary">{r.title}</span>
                      </div>
                      <div className="text-[11px] text-text-secondary mt-0.5">{r.access}</div>
                      <div className="text-[10px] text-text-muted font-mono mt-1 pt-1 border-t border-border/50">
                        <div>Email: {r.email}</div>
                        <div>Password: {r.password}</div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
