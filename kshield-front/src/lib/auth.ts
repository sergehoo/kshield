/**
 * Auth store — Zustand + persist localStorage.
 *
 * Contient l'access token, le refresh token, et un profil utilisateur minimal
 * (populé après un GET /api/v1/auth/me/ ou équivalent).
 */
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type AuthUser = {
  id: number | string;
  email: string;
  full_name?: string;
  is_superuser?: boolean;
  is_staff?: boolean;
  roles?: string[];
  tenant?: { id: number; name?: string; slug?: string } | null;
};

type Tokens = { accessToken: string; refreshToken: string };

type AuthState = {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;

  setTokens: (t: Tokens) => void;
  setUser: (u: AuthUser | null) => void;
  logout: () => void;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,

      setTokens: ({ accessToken, refreshToken }) =>
        set(() => ({ accessToken, refreshToken, isAuthenticated: !!accessToken })),

      setUser: (u) => set(() => ({ user: u })),

      logout: () =>
        set(() => ({
          accessToken: null,
          refreshToken: null,
          user: null,
          isAuthenticated: false,
        })),
    }),
    {
      name: "kshield-auth",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        accessToken: s.accessToken,
        refreshToken: s.refreshToken,
        user: s.user,
        isAuthenticated: s.isAuthenticated,
      }),
    },
  ),
);
