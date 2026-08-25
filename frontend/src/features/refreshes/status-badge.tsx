import { Badge } from "@/components/ui/badge";

export function RefreshStatusBadge({
  status,
}: {
  status: string;
}): React.JSX.Element {
  if (status === "succeeded") return <Badge variant="outline">Succeeded</Badge>;
  if (status === "partial") return <Badge variant="secondary">Partial</Badge>;
  if (status === "failed") return <Badge variant="destructive">Failed</Badge>;
  if (status === "running") return <Badge variant="secondary">Running</Badge>;
  return <Badge variant="outline">Cancelled</Badge>;
}
