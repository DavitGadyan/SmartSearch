"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export function useAdmin<T>(path: string, params?: Record<string, string | number | boolean | undefined>, enabled = true) {
  return useQuery({ queryKey: ["admin", path, params], queryFn: () => api.admin.get<T>(path, params), enabled });
}

export type { Overview } from "./api";
