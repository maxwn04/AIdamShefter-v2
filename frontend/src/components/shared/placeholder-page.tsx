import type { LucideIcon } from "lucide-react";

interface PlaceholderPageProps {
  eyebrow: string;
  title: string;
  description: string;
  icon: LucideIcon;
  detail?: string;
}

export function PlaceholderPage({
  eyebrow,
  title,
  description,
  icon: Icon,
  detail,
}: PlaceholderPageProps): React.JSX.Element {
  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
      <header className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          {eyebrow}
        </p>
        <h1 className="mt-3 font-editorial text-4xl font-semibold tracking-tight sm:text-5xl">
          {title}
        </h1>
        <p className="mt-4 text-base leading-7 text-muted-foreground">
          {description}
        </p>
      </header>

      <section className="mt-10 flex min-h-64 items-center justify-center rounded-lg border border-dashed border-border bg-card/60 p-8 text-center">
        <div className="max-w-md">
          <div className="mx-auto flex size-12 items-center justify-center rounded-full border border-border bg-background">
            <Icon className="size-5 text-muted-foreground" aria-hidden="true" />
          </div>
          <h2 className="mt-5 font-editorial text-xl font-semibold">
            Foundation ready
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {detail ?? "This workspace is ready for its product workflow."}
          </p>
        </div>
      </section>
    </div>
  );
}
