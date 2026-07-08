/**
 * useLive — abonnement "temps réel" léger via polling TanStack Query.
 *
 * L'API Django ne fournit pas (encore) de websockets, donc on simule le live
 * en pollant à intervalle court quand l'onglet est actif. Quand l'utilisateur
 * quitte l'onglet, refetchIntervalInBackground=false stoppe le polling pour
 * économiser la bande passante et éviter d'invalider les rate-limits DRF.
 */
import { useQuery } from "@tanstack/react-query";

const DEFAULT_POLL = Number(import.meta.env.VITE_LIVE_POLL_MS || 15_000);

type Options = {
  intervalMs?: number;
  paused?: boolean;
  enabled?: boolean;
  staleTime?: number;
  refetchOnMount?: boolean;
  refetchOnWindowFocus?: boolean;
};

export function useLive<T>(
  queryKey: unknown[],
  queryFn: () => Promise<T>,
  options: Options = {},
) {
  const { intervalMs, paused, enabled, ...rest } = options;
  return useQuery<T>({
    queryKey,
    queryFn,
    enabled: enabled ?? true,
    refetchInterval: paused ? false : intervalMs ?? DEFAULT_POLL,
    refetchIntervalInBackground: false,
    ...rest,
  });
}
