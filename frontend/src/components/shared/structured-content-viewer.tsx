import { Check, ChevronRight, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type CopyStatus = "idle" | "copied" | "failed";

function serializedContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (content === undefined) return "";
  return JSON.stringify(content, null, 2);
}

export interface StructuredContentViewerProps {
  className?: string;
  content: unknown;
  defaultOpen?: boolean;
  title: string;
}

export function StructuredContentViewer({
  className,
  content,
  defaultOpen = false,
  title,
}: StructuredContentViewerProps): React.JSX.Element {
  const [copyStatus, setCopyStatus] = useState<CopyStatus>("idle");
  const resetTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const hasContent = content !== undefined;
  const displayContent = serializedContent(content);
  const contentKind = typeof content === "string" ? "Text" : "JSON";

  useEffect(
    () => () => {
      if (resetTimer.current !== undefined) clearTimeout(resetTimer.current);
    },
    [],
  );

  async function copyContent(): Promise<void> {
    if (!hasContent) return;
    if (resetTimer.current !== undefined) clearTimeout(resetTimer.current);
    try {
      await navigator.clipboard.writeText(displayContent);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
    }
    resetTimer.current = setTimeout(() => {
      setCopyStatus("idle");
    }, 2_000);
  }

  return (
    <details
      className={cn(
        "group min-w-0 overflow-hidden rounded-md border border-border bg-card",
        className,
      )}
      open={defaultOpen || undefined}
    >
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-4 py-2 text-sm outline-none transition-colors hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        <ChevronRight
          className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90"
          aria-hidden="true"
        />
        <span className="min-w-0 flex-1 truncate font-medium">{title}</span>
        <span className="shrink-0 font-mono text-[0.7rem] uppercase tracking-wide text-muted-foreground">
          {hasContent ? contentKind : "Empty"}
        </span>
      </summary>

      <div className="min-w-0 border-t border-border">
        <div className="flex min-h-10 flex-wrap items-center justify-end gap-2 border-b border-border bg-muted/30 px-3 py-1.5">
          <span aria-live="polite" className="text-xs text-muted-foreground">
            {copyStatus === "failed" ? "Copy unavailable" : null}
          </span>
          <Button
            aria-label={
              copyStatus === "copied"
                ? `${title} copied`
                : `Copy exact ${title.toLowerCase()}`
            }
            disabled={!hasContent}
            onClick={() => void copyContent()}
            size="sm"
            type="button"
            variant="ghost"
          >
            {copyStatus === "copied" ? (
              <Check className="size-3.5" aria-hidden="true" />
            ) : (
              <Copy className="size-3.5" aria-hidden="true" />
            )}
            {copyStatus === "copied" ? "Copied" : "Copy"}
          </Button>
        </div>

        {hasContent ? (
          <pre className="max-h-[32rem] max-w-full overflow-auto bg-muted/20 p-4 font-mono text-xs leading-5 whitespace-pre">
            <code>{displayContent}</code>
          </pre>
        ) : (
          <p className="px-4 py-6 text-sm text-muted-foreground">
            No payload was recorded.
          </p>
        )}
      </div>
    </details>
  );
}
