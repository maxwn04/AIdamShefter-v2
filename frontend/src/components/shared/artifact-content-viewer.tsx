import { Check, Copy, FileWarning } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { MarkdownArticle } from "@/components/shared/markdown-article";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const MARKDOWN_MEDIA_TYPES = new Set([
  "application/markdown",
  "text/markdown",
  "text/x-markdown",
]);

const TEXT_APPLICATION_MEDIA_TYPES = new Set([
  "application/graphql",
  "application/javascript",
  "application/sql",
  "application/x-httpd-php",
  "application/x-javascript",
  "application/x-sh",
  "application/x-yaml",
  "application/xml",
  "application/yaml",
]);

type CopyStatus = "idle" | "copied" | "failed";
type PreviewKind = "json" | "markdown" | "source" | "unsupported";

function normalizedMediaType(mediaType: string): string {
  return mediaType.split(";", 1)[0]?.trim().toLowerCase() ?? "";
}

function previewKind(mediaType: string): PreviewKind {
  if (MARKDOWN_MEDIA_TYPES.has(mediaType)) return "markdown";
  if (mediaType === "application/json" || mediaType.endsWith("+json")) {
    return "json";
  }
  if (
    mediaType.startsWith("text/") ||
    mediaType.endsWith("+xml") ||
    TEXT_APPLICATION_MEDIA_TYPES.has(mediaType)
  ) {
    return "source";
  }
  return "unsupported";
}

function prettyJson(content: string): string {
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return content;
  }
}

function SourcePreview({ content }: { content: string }): React.JSX.Element {
  if (content.length === 0) {
    return (
      <p className="px-5 py-8 text-sm text-muted-foreground">
        This artifact version is empty.
      </p>
    );
  }

  return (
    <pre className="max-h-[70vh] max-w-full overflow-auto p-5 font-mono text-sm leading-6 whitespace-pre">
      <code>{content}</code>
    </pre>
  );
}

export interface ArtifactContentViewerProps {
  className?: string;
  content: string;
  mediaType: string;
}

export function ArtifactContentViewer({
  className,
  content,
  mediaType,
}: ArtifactContentViewerProps): React.JSX.Element {
  const [copyStatus, setCopyStatus] = useState<CopyStatus>("idle");
  const resetTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const normalizedType = normalizedMediaType(mediaType);
  const kind = previewKind(normalizedType);

  useEffect(
    () => () => {
      if (resetTimer.current !== undefined) clearTimeout(resetTimer.current);
    },
    [],
  );

  async function copyContent(): Promise<void> {
    if (resetTimer.current !== undefined) clearTimeout(resetTimer.current);
    try {
      await navigator.clipboard.writeText(content);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
    }
    resetTimer.current = setTimeout(() => {
      setCopyStatus("idle");
    }, 2_000);
  }

  return (
    <section className={cn("min-w-0", className)}>
      <div className="mb-3 flex min-h-9 flex-wrap items-center justify-between gap-3">
        <p className="font-mono text-xs text-muted-foreground">
          {normalizedType || "Unknown media type"}
        </p>
        <div className="flex items-center gap-2">
          <span aria-live="polite" className="text-xs text-muted-foreground">
            {copyStatus === "failed" ? "Copy unavailable" : null}
          </span>
          <Button
            aria-label={
              copyStatus === "copied"
                ? "Artifact content copied"
                : "Copy exact artifact content"
            }
            onClick={() => void copyContent()}
            size="sm"
            type="button"
            variant="outline"
          >
            {copyStatus === "copied" ? (
              <Check className="size-3.5" aria-hidden="true" />
            ) : (
              <Copy className="size-3.5" aria-hidden="true" />
            )}
            {copyStatus === "copied" ? "Copied" : "Copy content"}
          </Button>
        </div>
      </div>

      {kind === "markdown" ? (
        <div className="min-w-0 rounded-md border border-border bg-card p-5 sm:p-8">
          {content.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              This artifact version is empty.
            </p>
          ) : (
            <MarkdownArticle content={content} />
          )}
        </div>
      ) : null}

      {kind === "json" || kind === "source" ? (
        <div className="min-w-0 overflow-hidden rounded-md border border-border bg-muted/40">
          <SourcePreview
            content={kind === "json" ? prettyJson(content) : content}
          />
        </div>
      ) : null}

      {kind === "unsupported" ? (
        <div className="flex gap-3 rounded-md border border-border bg-muted/40 p-5">
          <FileWarning
            className="mt-0.5 size-5 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
          <div>
            <p className="text-sm font-medium">Preview unavailable</p>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
              This media type is not rendered in the browser. You can still copy
              the exact stored content for inspection in an appropriate tool.
            </p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
