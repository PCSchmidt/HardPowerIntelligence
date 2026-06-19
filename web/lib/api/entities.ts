import { apiFetch } from "@/lib/api/client";
import type { EntityDetail } from "@/lib/types";

export function getEntity(id: string) {
  return apiFetch<EntityDetail>(`/entities/${id}`);
}
