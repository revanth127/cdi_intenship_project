import React, { useState, useEffect } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthContext';
import {
  LayoutDashboard,
  ShoppingCart,
  Boxes,
  Factory,
  CreditCard,
  FileSpreadsheet,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  Menu,
  X,
  RotateCcw,
  LogOut,
  Plus,
  Truck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/components/ui/button';
import { useSyncStatus } from '@/lib/offline/useSyncStatus';
import { initSyncEngine } from '@/lib/offline/syncEngine';
import { getUnsentOrdersCount, clearAllOfflineData } from '@/lib/offline/db';
import { SignOutConfirmDialog } from '@/features/salesman/SignOutConfirmDialog';
import { ReAuthDialog } from '@/features/auth/ReAuthDialog';

interface NavItemConfig {
  label: string;
  to: string;
  icon: React.ElementType;
  roles: ('OWNER' | 'ADMIN' | 'SALESMAN' | 'PRODUCTION' | 'ACCOUNTANT')[];
}

const ALL_NAV_ITEMS: NavItemConfig[] = [
  // OWNER
  { label: 'Overview', to: '/', icon: LayoutDashboard, roles: ['OWNER'] },
  // ADMIN
  { label: 'Orders', to: '/orders', icon: ShoppingCart, roles: ['ADMIN'] },
  { label: 'Invoices', to: '/invoices', icon: FileSpreadsheet, roles: ['ADMIN'] },
  { label: 'Receivables', to: '/receivables', icon: CreditCard, roles: ['ADMIN'] },
  { label: 'Stock', to: '/stock', icon: Boxes, roles: ['ADMIN'] },
  { label: 'Production', to: '/production', icon: Factory, roles: ['ADMIN'] },
  { label: 'Purchases', to: '/purchases', icon: Truck, roles: ['ADMIN'] },
  // PRODUCTION
  { label: 'Purchases', to: '/purchases', icon: Truck, roles: ['PRODUCTION'] },
  { label: 'Stock', to: '/stock', icon: Boxes, roles: ['PRODUCTION'] },
  { label: 'Production', to: '/production', icon: Factory, roles: ['PRODUCTION'] },
  // ACCOUNTANT
  { label: 'Orders', to: '/orders', icon: ShoppingCart, roles: ['ACCOUNTANT'] },
  { label: 'Receivables', to: '/receivables', icon: CreditCard, roles: ['ACCOUNTANT'] },
  { label: 'Invoices', to: '/invoices', icon: FileSpreadsheet, roles: ['ACCOUNTANT'] },
  { label: 'Stock', to: '/stock', icon: Boxes, roles: ['ACCOUNTANT'] },
  { label: 'Reports', to: '/reports', icon: FileSpreadsheet, roles: ['ACCOUNTANT'] },
  // SALESMAN
  { label: 'New Order', to: '/orders/new', icon: Plus, roles: ['SALESMAN'] },
  { label: 'My Orders', to: '/orders/my', icon: ShoppingCart, roles: ['SALESMAN'] },
];

export const AppShell: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { status, triggerSync } = useSyncStatus();

  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [confirmSignOutOpen, setConfirmSignOutOpen] = useState(false);
  const [reAuthOpen, setReAuthOpen] = useState(false);
  const [unsentCount, setUnsentCount] = useState(0);

  const [lastUpdated, setLastUpdated] = useState(() => {
    const d = new Date();
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  });

  // Start sync engine triggers on mount
  useEffect(() => {
    const cleanup = initSyncEngine();
    return cleanup;
  }, []);

  // Listen for 401 re-auth prompt
  useEffect(() => {
    const handleAuthRequired = () => {
      setReAuthOpen(true);
    };
    window.addEventListener('sync:auth-required', handleAuthRequired);
    return () => window.removeEventListener('sync:auth-required', handleAuthRequired);
  }, []);

  // Also open reAuthDialog if status indicates paused for auth
  useEffect(() => {
    if (status.isPausedForAuth) {
      setReAuthOpen(true);
    }
  }, [status.isPausedForAuth]);

  const handleRefresh = () => {
    const d = new Date();
    setLastUpdated(`${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`);
    window.dispatchEvent(new CustomEvent('dashboard:refresh'));
    triggerSync();
  };

  const handleSignOutClick = async () => {
    const count = await getUnsentOrdersCount();
    if (count > 0) {
      setUnsentCount(count);
      setConfirmSignOutOpen(true);
    } else {
      await clearAllOfflineData();
      logout();
      navigate('/login');
    }
  };

  const handleConfirmSignOut = async () => {
    await clearAllOfflineData();
    logout();
    navigate('/login');
  };

  // Filter navigation items by active user role
  const allowedNavItems = ALL_NAV_ITEMS.filter(
    (item) => user && item.roles.includes(user.role)
  );

  const sendingOrdersCount = status.sendingCount || status.totalPendingCount || 1;

  return (
    <div className="min-h-screen bg-page flex">
      {/* Sign Out Warning Dialog */}
      <SignOutConfirmDialog
        open={confirmSignOutOpen}
        onOpenChange={setConfirmSignOutOpen}
        unsentCount={unsentCount}
        onConfirmSignOut={handleConfirmSignOut}
      />

      {/* Re-Authentication Dialog (triggered on 401 during sync) */}
      <ReAuthDialog open={reAuthOpen} onOpenChange={setReAuthOpen} />

      {/* Mobile Drawer Backdrop */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 bg-slate-900/50 z-40 lg:hidden"
          onClick={() => setIsMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Fixed Left Sidebar / Mobile Drawer */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 bg-surface border-r border-border transition-all duration-200 flex flex-col',
          isCollapsed ? 'w-16' : 'w-60',
          isMobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        )}
      >
        {/* Sidebar Header */}
        <div className="h-14 border-b border-border flex items-center justify-between px-3.5">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="w-7 h-7 rounded-[4px] bg-accent flex items-center justify-center text-white shrink-0">
              <Factory className="w-4 h-4" />
            </div>
            {!isCollapsed && (
              <div className="truncate">
                <span className="text-xs font-semibold text-text-primary tracking-tight block truncate">
                  Sri Murugan Foods
                </span>
                <span className="text-[11px] text-text-muted block">Operations Console</span>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="hidden lg:flex p-1 text-text-muted hover:text-text-primary rounded-[4px] hover:bg-surface-subtle"
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </button>
          <button
            type="button"
            onClick={() => setIsMobileOpen(false)}
            className="lg:hidden p-1 text-text-muted hover:text-text-primary"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto" aria-label="Main Navigation">
          {allowedNavItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setIsMobileOpen(false)}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2.5 px-2.5 py-2 rounded-[6px] text-xs font-medium transition-colors select-none',
                    isActive
                      ? 'bg-accent text-white font-semibold'
                      : 'text-text-secondary hover:text-text-primary hover:bg-surface-subtle'
                  )
                }
                title={isCollapsed ? item.label : undefined}
              >
                <Icon className="w-4 h-4 shrink-0" />
                {!isCollapsed && <span className="truncate">{item.label}</span>}
              </NavLink>
            );
          })}
        </nav>

        {/* User Footer in Sidebar */}
        <div className="p-3 border-t border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-7 h-7 rounded-full bg-surface-subtle border border-border flex items-center justify-center text-xs font-semibold text-text-primary shrink-0">
                {user?.full_name ? user.full_name[0] : 'U'}
              </div>
              {!isCollapsed && (
                <div className="truncate text-left min-w-0">
                  <div className="text-xs font-semibold text-text-primary truncate">
                    {user?.full_name || 'Operations User'}
                  </div>
                  <div className="text-[11px] text-text-muted font-mono">{user?.role}</div>
                </div>
              )}
            </div>
            {!isCollapsed && (
              <button
                type="button"
                onClick={handleSignOutClick}
                className="p-1 text-text-muted hover:text-status-breach-text rounded-[4px] hover:bg-status-breach-bg transition-colors"
                title="Sign out"
                aria-label="Sign out"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div
        className={cn(
          'flex-1 flex flex-col transition-all duration-200 min-w-0',
          isCollapsed ? 'lg:pl-16' : 'lg:pl-60'
        )}
      >
        {/* Top Bar */}
        <header className="h-14 bg-surface border-b border-border sticky top-0 z-30 px-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setIsMobileOpen(true)}
              className="lg:hidden p-1.5 text-text-secondary hover:text-text-primary rounded-[4px]"
              aria-label="Open navigation menu"
            >
              <Menu className="w-5 h-5" />
            </button>
            <h1 className="text-sm font-semibold text-text-primary tracking-tight">
              Sri Murugan Foods
            </h1>

            {/* Top Bar Status Text: Online, Offline, or "Sending 2 orders" */}
            <div className="flex items-center pl-2 border-l border-border" data-testid="topbar-connectivity">
              {status.isSyncing || status.sendingCount > 0 ? (
                <span
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-[4px] bg-blue-50 text-blue-700 text-xs font-semibold"
                  data-testid="status-sending"
                >
                  <RotateCcw className="w-3 h-3 animate-spin text-blue-600" />
                  <span>
                    Sending {sendingOrdersCount} {sendingOrdersCount === 1 ? 'order' : 'orders'}
                  </span>
                </span>
              ) : !status.isOnline ? (
                <span
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-[4px] bg-status-warning-bg text-status-warning-text border border-status-warning-border text-xs font-semibold"
                  data-testid="status-offline"
                >
                  <span className="w-2 h-2 rounded-full bg-amber-500" />
                  <span>Offline</span>
                </span>
              ) : (
                <span
                  className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[4px] text-xs font-medium text-text-secondary"
                  data-testid="status-online"
                >
                  <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  <span>Online</span>
                </span>
              )}
            </div>
          </div>

          {/* Right Top Actions: Refresh & User Menu */}
          <div className="flex items-center gap-3">
            {/* Refresh Action with "Updated hh:mm" */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-text-muted hidden sm:inline tabular-nums">
                Updated {lastUpdated}
              </span>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleRefresh}
                className="h-8 text-xs gap-1.5"
                title="Refresh operations data"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Refresh</span>
              </Button>
            </div>

            {/* User Profile Chip */}
            <div className="flex items-center gap-2 pl-2 border-l border-border">
              <div className="text-right hidden sm:block">
                <span className="text-xs font-semibold text-text-primary block leading-tight">
                  {user?.full_name}
                </span>
                <span className="text-[11px] text-text-muted uppercase tracking-wider block">
                  {user?.role}
                </span>
              </div>
              <button
                type="button"
                onClick={handleSignOutClick}
                className="h-8 px-2 text-xs text-text-secondary hover:text-text-primary border border-border rounded-[4px] hover:bg-surface-subtle inline-flex items-center gap-1"
                title="Sign out"
                data-testid="topbar-signout-button"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Sign out</span>
              </button>
            </div>
          </div>
        </header>

        {/* Page Content Landmark */}
        <main className="flex-1 p-4 lg:p-6 max-w-7xl w-full mx-auto" role="main">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
