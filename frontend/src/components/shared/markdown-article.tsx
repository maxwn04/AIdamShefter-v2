import type * as React from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

const markdownComponents: Components = {
  a({ className, href, node, ...props }) {
    void node;
    const opensNewWindow =
      href?.startsWith("https://") === true ||
      href?.startsWith("http://") === true;

    return (
      <a
        className={cn(
          "font-medium text-primary underline decoration-primary/35 underline-offset-4 transition-colors hover:decoration-primary",
          className,
        )}
        {...props}
        href={href}
        rel={opensNewWindow ? "noreferrer noopener" : undefined}
        target={opensNewWindow ? "_blank" : undefined}
      />
    );
  },
  table({ className, node, ...props }) {
    void node;
    return (
      <div
        aria-label="Scrollable article table"
        className="my-7 max-w-full overflow-x-auto rounded-md border border-border"
        role="region"
        tabIndex={0}
      >
        <table
          className={cn("w-full min-w-max border-collapse text-sm", className)}
          {...props}
        />
      </div>
    );
  },
  img({ alt, node }) {
    void node;
    return (
      <span className="my-6 block rounded-md border border-dashed border-border bg-muted/60 px-4 py-3 font-sans text-sm text-muted-foreground">
        Image omitted{alt ? `: ${alt}` : ""}
      </span>
    );
  },
};

export interface MarkdownArticleProps {
  className?: string;
  content: string;
}

export function MarkdownArticle({
  className,
  content,
}: MarkdownArticleProps): React.JSX.Element {
  return (
    <article
      className={cn(
        "min-w-0 font-editorial text-[1.05rem] leading-8 text-foreground",
        "[&_h1]:mb-7 [&_h1]:mt-2 [&_h1]:text-4xl [&_h1]:font-semibold [&_h1]:leading-tight [&_h1]:tracking-tight sm:[&_h1]:text-5xl",
        "[&_h2]:mb-4 [&_h2]:mt-12 [&_h2]:text-3xl [&_h2]:font-semibold [&_h2]:leading-tight [&_h2]:tracking-tight",
        "[&_h3]:mb-3 [&_h3]:mt-9 [&_h3]:text-2xl [&_h3]:font-semibold [&_h3]:leading-snug",
        "[&_h4]:mb-3 [&_h4]:mt-8 [&_h4]:text-xl [&_h4]:font-semibold",
        "[&_p]:my-5 [&_p]:max-w-[76ch]",
        "[&_ul]:my-5 [&_ul]:max-w-[76ch] [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-7",
        "[&_ol]:my-5 [&_ol]:max-w-[76ch] [&_ol]:list-decimal [&_ol]:space-y-2 [&_ol]:pl-7",
        "[&_li>p]:my-0",
        "[&_blockquote]:my-8 [&_blockquote]:max-w-[72ch] [&_blockquote]:border-l-4 [&_blockquote]:border-primary/40 [&_blockquote]:pl-6 [&_blockquote]:italic [&_blockquote]:text-muted-foreground",
        "[&_hr]:my-10 [&_hr]:border-border",
        "[&_strong]:font-semibold",
        "[&_pre]:my-7 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:border [&_pre]:border-border [&_pre]:bg-muted [&_pre]:p-4 [&_pre]:font-mono [&_pre]:text-sm [&_pre]:leading-6",
        "[&_code]:break-words [&_code]:rounded [&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.9em] [&_pre_code]:break-normal [&_pre_code]:bg-transparent [&_pre_code]:p-0",
        "[&_th]:border-b [&_th]:border-r [&_th]:border-border [&_th]:bg-muted [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-sans [&_th]:text-xs [&_th]:font-semibold [&_th]:uppercase [&_th]:tracking-wide [&_th:last-child]:border-r-0",
        "[&_td]:border-b [&_td]:border-r [&_td]:border-border [&_td]:px-3 [&_td]:py-2 [&_td]:align-top [&_td:last-child]:border-r-0 [&_tr:last-child_td]:border-b-0",
        className,
      )}
    >
      <ReactMarkdown
        components={markdownComponents}
        remarkPlugins={[remarkGfm]}
        skipHtml
      >
        {content}
      </ReactMarkdown>
    </article>
  );
}
