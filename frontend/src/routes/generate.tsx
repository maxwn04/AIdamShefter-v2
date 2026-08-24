import { PlusCircle } from "lucide-react";

import { PlaceholderPage } from "@/components/shared/placeholder-page";

export function Component(): React.JSX.Element {
  return (
    <PlaceholderPage
      eyebrow="Reporter assignment"
      title="Generate"
      description="Configure the factual boundary, assignment, voice, and ordered model chain for a durable reporter run."
      detail="The generation form and submission workflow will be added after league management."
      icon={PlusCircle}
    />
  );
}
