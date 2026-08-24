import { Library } from "lucide-react";

import { PlaceholderPage } from "@/components/shared/placeholder-page";

export function Component(): React.JSX.Element {
  return (
    <PlaceholderPage
      eyebrow="Submitted work"
      title="Articles"
      description="Browse exact submitted article versions and open the generation record behind each one."
      detail="Article history and audit views are reserved for the article journey layer."
      icon={Library}
    />
  );
}
