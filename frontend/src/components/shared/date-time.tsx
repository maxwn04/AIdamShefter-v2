import { formatExactDateTime, formatRelativeDateTime } from "@/lib/date-time";

interface DateTimeProps {
  value: string | null;
  empty?: string;
  showExact?: boolean;
}

export function DateTime({
  value,
  empty = "Not yet",
  showExact = false,
}: DateTimeProps): React.JSX.Element {
  if (!value) return <span className="text-muted-foreground">{empty}</span>;

  const exact = formatExactDateTime(value);
  return (
    <span className="inline-flex flex-col" title={exact}>
      <time dateTime={value}>{formatRelativeDateTime(value)}</time>
      {showExact ? (
        <span className="text-xs text-muted-foreground">{exact}</span>
      ) : null}
    </span>
  );
}
