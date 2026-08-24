import { Trophy } from "lucide-react";

import { PlaceholderPage } from "@/components/shared/placeholder-page";

export function Component(): React.JSX.Element {
  return (
    <PlaceholderPage
      eyebrow="League desk"
      title="Leagues"
      description="Choose the competition and season the reporter should work in. League management arrives in the next product layer."
      detail="Competition browsing, creation, and archive controls will live here."
      icon={Trophy}
    />
  );
}
