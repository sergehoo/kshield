import { QueryClient } from "@tanstack/react-query";

/**
 * Client TanStack Query configuré pour KAYDAN SHIELD.
 *
 * Défauts sains :
 * - staleTime 10s (évite les re-fetch trop agressifs)
 * - retry 1 (le backend Django peut lâcher 502/504 pendant les rebuild Dokploy)
 * - refetchOnWindowFocus true (utile pour un cockpit)
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      gcTime: 5 * 60_000,
      retry: (failureCount, error: any) => {
        // Ne retry pas les 401/403/404
        const status = error?.response?.status;
        if (status === 401 || status === 403 || status === 404) return false;
        return failureCount < 1;
      },
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
    },
    mutations: {
      retry: 0,
    },
  },
});
