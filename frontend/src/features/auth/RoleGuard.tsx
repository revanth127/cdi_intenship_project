import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';

export interface RoleGuardProps {
  allowedRoles: ('OWNER' | 'ADMIN' | 'SALESMAN' | 'PRODUCTION' | 'ACCOUNTANT')[];
  children: React.ReactNode;
}

export const RoleGuard: React.FC<RoleGuardProps> = ({ allowedRoles, children }) => {
  const { user, isAuthenticated, logout } = useAuth();

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  if (!allowedRoles.includes(user.role)) {
    return (
      <div
        className="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center"
        data-testid="guard-restricted"
      >
        <div className="w-12 h-12 rounded-[6px] bg-status-breach-bg border border-status-breach-border flex items-center justify-center text-status-breach-text mb-4">
          <ShieldAlert className="w-6 h-6" aria-hidden="true" />
        </div>
        <h1 className="text-lg font-semibold text-text-primary tracking-tight">
          Access restricted
        </h1>
        <p className="mt-1 text-sm text-text-secondary max-w-md">
          Your role ({user.role}) is not authorized to open this view. The operations dashboard is restricted to executive management.
        </p>
        <div className="mt-6 flex items-center gap-3">
          <Button variant="secondary" size="sm" onClick={() => window.history.back()}>
            Go back
          </Button>
          <Button variant="primary" size="sm" onClick={logout}>
            Sign in as another user
          </Button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
};
