import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../AuthContext';
import { LoginPage } from '../LoginPage';
import { getAccessToken, setAccessToken } from '@/lib/api/client';

describe('AuthProvider backend authentication', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    sessionStorage.clear();
    localStorage.clear();
    setAccessToken(null);
  });

  it('does not create a session when the backend rejects login', async () => {
    vi.stubEnv('VITE_DEMO_MODE', 'false');
    sessionStorage.clear();
    localStorage.clear();
    setAccessToken(null);
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Incorrect email or password' }),
    })));

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>
    );

    fireEvent.change(screen.getByPlaceholderText('user@foodmfr.local'), {
      target: { value: 'owner@foodmfr.local' },
    });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), {
      target: { value: 'wrong-password' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText('Incorrect email or password')).toBeInTheDocument();
    expect(getAccessToken()).toBeNull();
    expect(sessionStorage.getItem('user_profile')).toBeNull();
    expect(localStorage.getItem('user_profile')).toBeNull();
  });
});
