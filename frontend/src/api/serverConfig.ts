import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

interface ServerConfig {
  reviewer_mode: boolean;
  local_mode: boolean;
}

export function useServerConfig() {
  return useQuery({
    queryKey: ["server-config"],
    queryFn: () => apiFetch<ServerConfig>("/server-config"),
    staleTime: Infinity,
    retry: false,
  });
}
