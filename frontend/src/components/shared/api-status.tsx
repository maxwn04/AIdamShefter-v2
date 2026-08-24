import { useQuery } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, Radio } from "lucide-react";

import { getApiHealth } from "@/api/health";
import { queryKeys } from "@/api/query-keys";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export function ApiStatus(): React.JSX.Element {
  const health = useQuery({
    queryKey: queryKeys.health.status(),
    queryFn: ({ signal }) => getApiHealth(signal),
    refetchInterval: 30_000,
  });

  if (health.isPending) {
    return (
      <div className="flex items-center gap-2" aria-label="Checking API status">
        <Skeleton className="h-5 w-20" />
        <span className="sr-only">Checking API status</span>
      </div>
    );
  }

  if (health.isError) {
    return (
      <Badge variant="destructive" role="status">
        <CircleAlert className="size-3" aria-hidden="true" />
        API offline
      </Badge>
    );
  }

  if (health.data.state === "online") {
    return (
      <Badge variant="outline" role="status">
        <Radio className="size-3" aria-hidden="true" />
        {health.data.summary}
      </Badge>
    );
  }

  return (
    <Badge variant="secondary" role="status">
      <CircleCheck className="size-3" aria-hidden="true" />
      {health.data.summary}
    </Badge>
  );
}
