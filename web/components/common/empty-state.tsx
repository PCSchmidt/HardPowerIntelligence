import { Clock } from "lucide-react";

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border py-16 text-center">
      <Clock size={24} className="text-muted-foreground" />
      <p className="font-display text-display-sm text-foreground">{title}</p>
      {hint && <p className="max-w-sm text-ui-md text-muted-foreground">{hint}</p>}
    </div>
  );
}
