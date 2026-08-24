import { LayoutDashboard } from "lucide-react";
import { useParams } from "react-router";

import { PlaceholderPage } from "@/components/shared/placeholder-page";

export function Component(): React.JSX.Element {
  const { competitionId } = useParams();
  return (
    <PlaceholderPage
      eyebrow="Competition overview"
      title="League operations"
      description="Season identity, Sleeper freshness, refresh history, and recent reporter activity will meet here."
      detail={`Competition scope: ${competitionId ?? "unknown"}`}
      icon={LayoutDashboard}
    />
  );
}
