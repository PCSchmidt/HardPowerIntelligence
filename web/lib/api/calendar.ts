import { apiFetch } from "@/lib/api/client";
import type { CalendarEvent, Desk } from "@/lib/types";

export function getCalendar(desk: Desk) {
  return apiFetch<{ events: CalendarEvent[] }>(`/calendar?desk=${desk}`);
}
