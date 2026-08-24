export type FieldErrors = Record<string, string[]>;

export interface ApiErrorOptions {
  status: number;
  code: string;
  summary: string;
  fieldErrors?: FieldErrors;
  correlationId?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fieldErrors: FieldErrors;
  readonly correlationId?: string;

  constructor(options: ApiErrorOptions) {
    super(options.summary);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.fieldErrors = options.fieldErrors ?? {};
    this.correlationId = options.correlationId;
  }
}

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function parseFieldErrors(value: unknown): FieldErrors {
  if (!isRecord(value)) return {};

  return Object.fromEntries(
    Object.entries(value).flatMap(([field, messages]) => {
      if (!Array.isArray(messages)) return [];
      const parsed = messages.filter(
        (message): message is string => typeof message === "string",
      );
      return parsed.length > 0 ? [[field, parsed]] : [];
    }),
  );
}

function parseValidationErrors(detail: unknown): FieldErrors {
  if (!Array.isArray(detail)) return {};

  const errors: FieldErrors = {};
  for (const item of detail) {
    if (!isRecord(item) || !Array.isArray(item.loc)) continue;
    const field = item.loc
      .filter((part) => part !== "body" && part !== "query" && part !== "path")
      .map(String)
      .join(".");
    const message = asString(item.msg);
    if (!field || !message) continue;
    errors[field] = [...(errors[field] ?? []), message];
  }
  return errors;
}

export function normalizeApiError(
  status: number,
  payload: unknown,
  responseCorrelationId?: string,
): ApiError {
  if (isRecord(payload) && isRecord(payload.error)) {
    const error = payload.error;
    return new ApiError({
      status,
      code: asString(error.code) ?? `http_${String(status)}`,
      summary: asString(error.summary) ?? "The request could not be completed.",
      fieldErrors: parseFieldErrors(error.field_errors),
      correlationId:
        asString(error.correlation_id) ?? responseCorrelationId ?? undefined,
    });
  }

  if (isRecord(payload)) {
    const detail = payload.detail;
    const fieldErrors = parseValidationErrors(detail);
    const isValidationError = Object.keys(fieldErrors).length > 0;
    return new ApiError({
      status,
      code: isValidationError ? "validation_error" : `http_${String(status)}`,
      summary:
        asString(detail) ??
        (isValidationError
          ? "Review the highlighted fields and try again."
          : "The request could not be completed."),
      fieldErrors,
      correlationId: responseCorrelationId,
    });
  }

  return new ApiError({
    status,
    code: `http_${String(status)}`,
    summary:
      asString(payload) ??
      (status === 0
        ? "The API could not be reached."
        : "The request could not be completed."),
    correlationId: responseCorrelationId,
  });
}
