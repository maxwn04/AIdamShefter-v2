import { FileText } from "lucide-react";
import { useParams } from "react-router";

import { PlaceholderPage } from "@/components/shared/placeholder-page";

export function Component(): React.JSX.Element {
  const { generationId } = useParams();
  return (
    <PlaceholderPage
      eyebrow="Generation record"
      title="Run detail"
      description="Durable run status, the submitted article, artifacts, execution, and usage will be inspected here."
      detail={`Generation scope: ${generationId ?? "unknown"}`}
      icon={FileText}
    />
  );
}
