import * as React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/features/auth/AuthContext';
import { RoleGuard } from '@/features/auth/RoleGuard';
import { LoginPage } from '@/features/auth/LoginPage';
import { AppShell } from '@/app/AppShell';
import { OwnerDashboardPage } from '@/features/dashboard/OwnerDashboardPage';
import { SalesmanOrderPage } from '@/features/salesman/SalesmanOrderPage';
import { SalesmanOrdersList } from '@/features/salesman/SalesmanOrdersList';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

// Simple placeholder page for subsidiary shell routes
const PlaceholderModule: React.FC<{ title: string; subtitle: string }> = ({ title, subtitle }) => (
  <div className="bg-surface border border-border rounded-[6px] p-8 text-center max-w-xl mx-auto my-12">
    <h2 className="text-base font-semibold text-text-primary tracking-tight">{title}</h2>
    <p className="text-xs text-text-secondary mt-1">{subtitle}</p>
  </div>
);

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />

            {/* Authenticated App Shell */}
            <Route
              path="/"
              element={
                <RoleGuard allowedRoles={['OWNER', 'ADMIN', 'ACCOUNTANT', 'SALESMAN', 'PRODUCTION']}>
                  <AppShell />
                </RoleGuard>
              }
            >
              {/* Executive Dashboard: Strictly restricted to OWNER, ADMIN, ACCOUNTANT */}
              <Route
                index
                element={
                  <RoleGuard allowedRoles={['OWNER', 'ADMIN', 'ACCOUNTANT']}>
                    <OwnerDashboardPage />
                  </RoleGuard>
                }
              />

              {/* Salesman Field Order Routes */}
              <Route path="orders" element={<SalesmanOrdersList />} />
              <Route path="orders/my" element={<SalesmanOrdersList />} />
              <Route path="orders/new" element={<SalesmanOrderPage />} />

              {/* Operations & Auditing Routes */}
              <Route
                path="stock"
                element={
                  <RoleGuard allowedRoles={['OWNER', 'ADMIN', 'PRODUCTION']}>
                    <PlaceholderModule
                      title="Stock Ledger"
                      subtitle="Immutable inventory ledger movements, weighted average valuation, and batch balances."
                    />
                  </RoleGuard>
                }
              />
              <Route
                path="production"
                element={
                  <RoleGuard allowedRoles={['OWNER', 'ADMIN', 'PRODUCTION']}>
                    <PlaceholderModule
                      title="Production Operations"
                      subtitle="Multi-pack BOM runs, actual consumption tracking, and yield variance flags."
                    />
                  </RoleGuard>
                }
              />
              <Route
                path="receivables"
                element={
                  <RoleGuard allowedRoles={['OWNER', 'ADMIN', 'ACCOUNTANT']}>
                    <PlaceholderModule
                      title="Receivables & Dues"
                      subtitle="Customer invoices, payments, credit note allocations, and ageing analysis."
                    />
                  </RoleGuard>
                }
              />
              <Route
                path="reports"
                element={
                  <RoleGuard allowedRoles={['OWNER', 'ADMIN', 'ACCOUNTANT']}>
                    <PlaceholderModule
                      title="Auditing & Tax Reports"
                      subtitle="HSN summary, GSTR-1 preparation, and inventory valuation certificates."
                    />
                  </RoleGuard>
                }
              />
            </Route>

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
