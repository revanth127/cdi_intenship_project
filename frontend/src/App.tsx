import * as React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from '@/features/auth/AuthContext';
import { RoleGuard } from '@/features/auth/RoleGuard';
import { LoginPage } from '@/features/auth/LoginPage';
import { AppShell } from '@/app/AppShell';
import { OwnerDashboardPage } from '@/features/dashboard/OwnerDashboardPage';
import { SalesmanOrderPage } from '@/features/salesman/SalesmanOrderPage';
import { SalesmanOrdersList } from '@/features/salesman/SalesmanOrdersList';
import { PurchasesPage } from '@/features/purchases/PurchasesPage';
import { StockLedgerPage } from '@/features/stock/StockLedgerPage';
import { ProductionOperationsPage } from '@/features/production/ProductionOperationsPage';
import { AdminOrdersPage } from '@/features/admin/orders/AdminOrdersPage';
import { InvoicesPage } from '@/features/admin/invoices/InvoicesPage';
import { ReceivablesPage } from '@/features/admin/receivables/ReceivablesPage';
import { ReportsPage } from '@/features/admin/reports/ReportsPage';

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

// Admin order inbox for admins; read-only inbox for accountants; salesman list otherwise
const OrdersRoute: React.FC = () => {
  const { user } = useAuth();
  if (user?.role === 'ADMIN') return <AdminOrdersPage />;
  if (user?.role === 'ACCOUNTANT') return <AdminOrdersPage isReadOnly />;
  return <SalesmanOrdersList />;
};

// Invoices are read-only for accountants; mutations require admin
const InvoicesRoute: React.FC = () => {
  const { user } = useAuth();
  return <InvoicesPage isReadOnly={user?.role !== 'ADMIN'} />;
};

// Receivables: payment recording is admin-only; accountant is read-only
const ReceivablesRoute: React.FC = () => {
  const { user } = useAuth();
  return <ReceivablesPage isReadOnly={user?.role !== 'ADMIN'} />;
};

// Dynamic landing page router directing each role to its dedicated home view
export const RoleLanding: React.FC = () => {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === 'SALESMAN') return <Navigate to="/orders/new" replace />;
  if (user.role === 'ADMIN') return <Navigate to="/orders" replace />;
  if (user.role === 'PRODUCTION') return <Navigate to="/production" replace />;
  if (user.role === 'ACCOUNTANT') return <Navigate to="/reports" replace />;
  return <OwnerDashboardPage />;
};

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
              {/* Home page for each role:
                  - salesman: New order (/orders/new)
                  - admin: Orders (/orders)
                  - production: Production (/production)
                  - accountant: Reports (/reports)
                  - owner: Overview (/)
              */}
              <Route index element={<RoleLanding />} />

              {/* Salesman Field Order Routes */}
              <Route
                path="orders"
                element={
                  <RoleGuard allowedRoles={['OWNER', 'ADMIN', 'SALESMAN', 'ACCOUNTANT']}>
                    <OrdersRoute />
                  </RoleGuard>
                }
              />
              <Route
                path="orders/my"
                element={
                  <RoleGuard allowedRoles={['SALESMAN', 'OWNER', 'ADMIN']}>
                    <SalesmanOrdersList />
                  </RoleGuard>
                }
              />
              <Route
                path="orders/new"
                element={
                  <RoleGuard allowedRoles={['SALESMAN', 'OWNER', 'ADMIN']}>
                    <SalesmanOrderPage />
                  </RoleGuard>
                }
              />

              {/* Operations & Auditing Routes */}
              <Route
                path="purchases"
                element={
                  <RoleGuard allowedRoles={['OWNER', 'ADMIN', 'PRODUCTION']}>
                    <PurchasesPage />
                  </RoleGuard>
                }
              />
              <Route
                path="stock"
                element={
                  <RoleGuard allowedRoles={['OWNER', 'ADMIN', 'PRODUCTION', 'ACCOUNTANT']}>
                    <StockLedgerPage />
                  </RoleGuard>
                }
              />
              <Route
                path="production"
                element={
                  <RoleGuard allowedRoles={['OWNER', 'ADMIN', 'PRODUCTION']}>
                    <ProductionOperationsPage />
                  </RoleGuard>
                }
              />
              <Route
                path="invoices"
                element={
                  <RoleGuard allowedRoles={['OWNER', 'ADMIN', 'ACCOUNTANT']}>
                    <InvoicesRoute />
                  </RoleGuard>
                }
              />
              <Route
                path="receivables"
                element={
                  <RoleGuard allowedRoles={['OWNER', 'ADMIN', 'ACCOUNTANT']}>
                    <ReceivablesRoute />
                  </RoleGuard>
                }
              />
              <Route
                path="reports"
                element={
                  <RoleGuard allowedRoles={['OWNER', 'ADMIN', 'ACCOUNTANT', 'PRODUCTION']}>
                    <ReportsPage />
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
