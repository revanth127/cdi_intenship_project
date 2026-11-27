import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Factory, Lock, Mail, ArrowRight, UserCheck } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const returnUrl = searchParams.get('returnUrl') || '/';
  const isExpired = searchParams.get('expired') === 'true';

  const [email, setEmail] = useState('owner@foodmfr.local');
  const [password, setPassword] = useState('OwnerPass123!');
  const [error, setError] = useState<string | null>(null);
  const { login, mockLoginAs, isLoading } = useAuth();
  const navigate = useNavigate();

  // Demo mode flag from env (default true for evaluation)
  const isDemoMode = import.meta.env.VITE_DEMO_MODE !== 'false';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await login(email, password);
      navigate(returnUrl);
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    }
  };

  const handleQuickLogin = (role: 'OWNER' | 'ADMIN' | 'SALESMAN' | 'PRODUCTION' | 'ACCOUNTANT') => {
    mockLoginAs(role);
    navigate('/');
  };

  return (
    <div className="min-h-screen bg-page flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-sm">
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

            {/* Test Logins Block (Only visible in Demo Mode via env flag) */}
            {isDemoMode && (
              <div className="mt-6 pt-5 border-t border-border">
                <div className="flex items-center gap-1.5 mb-2.5">
                  <UserCheck className="w-3.5 h-3.5 text-text-muted" />
                  <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Demo Mode Logins
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  <button
                    type="button"
                    onClick={() => handleQuickLogin('OWNER')}
                    className="px-2.5 py-1.5 text-left text-xs rounded-[4px] border border-border hover:bg-surface-subtle transition-colors"
                  >
                    <div className="font-semibold text-text-primary">Owner</div>
                    <div className="text-[11px] text-text-muted">Executive access</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleQuickLogin('ADMIN')}
                    className="px-2.5 py-1.5 text-left text-xs rounded-[4px] border border-border hover:bg-surface-subtle transition-colors"
                  >
                    <div className="font-semibold text-text-primary">Admin</div>
                    <div className="text-[11px] text-text-muted">Full system control</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleQuickLogin('SALESMAN')}
                    className="px-2.5 py-1.5 text-left text-xs rounded-[4px] border border-border hover:bg-surface-subtle transition-colors"
                  >
                    <div className="font-semibold text-text-primary">Salesman</div>
                    <div className="text-[11px] text-text-muted">Test 403 guard</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleQuickLogin('PRODUCTION')}
                    className="px-2.5 py-1.5 text-left text-xs rounded-[4px] border border-border hover:bg-surface-subtle transition-colors"
                  >
                    <div className="font-semibold text-text-primary">Production</div>
                    <div className="text-[11px] text-text-muted">Batch run logging</div>
                  </button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
