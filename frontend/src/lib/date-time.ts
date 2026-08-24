const relativeFormatter = new Intl.RelativeTimeFormat(undefined, {
  numeric: "auto",
});

const exactFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

const relativeUnits: readonly (readonly [
  Intl.RelativeTimeFormatUnit,
  number,
])[] = [
  ["year", 31_536_000],
  ["month", 2_592_000],
  ["week", 604_800],
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
  ["second", 1],
];

export function formatExactDateTime(value: string): string {
  return exactFormatter.format(new Date(value));
}

export function formatRelativeDateTime(
  value: string,
  now = new Date(),
): string {
  const date = new Date(value);
  const differenceSeconds = (date.getTime() - now.getTime()) / 1_000;
  const fallback: readonly [Intl.RelativeTimeFormatUnit, number] = [
    "second",
    1,
  ];
  const [unit, seconds] =
    relativeUnits.find(
      ([, threshold]) => Math.abs(differenceSeconds) >= threshold,
    ) ?? fallback;
  return relativeFormatter.format(
    Math.round(differenceSeconds / seconds),
    unit,
  );
}
