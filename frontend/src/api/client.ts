import type { AuthErrorCode, ValidationIssue } from "../auth/types";

const AUTH_ERROR_CODES = new Set<AuthErrorCode>([
  "authentication_required",
  "invalid_credentials",
  "account_conflict",
  "account_link_required",
  "csrf_failed",
  "rate_limited",
]);

interface ApiErrorOptions {
  status: number;
  message: string;
  code?: AuthErrorCode;
  retryAfterSeconds?: number;
  validationIssues?: ValidationIssue[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: AuthErrorCode;
  readonly retryAfterSeconds?: number;
  readonly validationIssues?: ValidationIssue[];

  constructor(options: ApiErrorOptions) {
    super(options.message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.retryAfterSeconds = options.retryAfterSeconds;
    this.validationIssues = options.validationIssues;
  }
}

export interface ApiRequestOptions {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  headers?: HeadersInit;
  signal?: AbortSignal;
}

export interface ApiClient {
  request<T>(path: string, options?: ApiRequestOptions): Promise<T>;
}

export function createApiClient(
  fetcher: typeof fetch = globalThis.fetch,
): ApiClient {
  return {
    async request<T>(
      path: string,
      options: ApiRequestOptions = {},
    ): Promise<T> {
      const headers = new Headers(options.headers);
      let body: string | undefined;
      if (options.body !== undefined) {
        headers.set("Content-Type", "application/json");
        body = JSON.stringify(options.body);
      }

      let response: Response;
      try {
        response = await fetcher(path, {
          method: options.method ?? "GET",
          headers,
          body,
          credentials: "include",
          signal: options.signal,
        });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          throw error;
        }
        throw new ApiError({ status: 0, message: "Network request failed." });
      }

      if (!response.ok) {
        throw await parseApiError(response);
      }
      if (response.status === 204) {
        return undefined as T;
      }

      try {
        return (await response.json()) as T;
      } catch {
        throw new ApiError({
          status: response.status,
          message: "Unexpected server response.",
        });
      }
    },
  };
}

async function parseApiError(response: Response): Promise<ApiError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }

  const detail = isRecord(payload) ? payload.detail : undefined;
  if (isRecord(detail)) {
    const code = detail.code;
    const message = detail.message;
    if (
      typeof code === "string" &&
      AUTH_ERROR_CODES.has(code as AuthErrorCode) &&
      typeof message === "string"
    ) {
      return new ApiError({
        status: response.status,
        code: code as AuthErrorCode,
        message,
        retryAfterSeconds: parseRetryAfter(response.headers.get("Retry-After")),
      });
    }
  }

  if (Array.isArray(detail)) {
    const validationIssues = detail.flatMap(parseValidationIssue);
    if (validationIssues.length > 0) {
      return new ApiError({
        status: response.status,
        message: "Request validation failed.",
        validationIssues,
      });
    }
  }

  return new ApiError({
    status: response.status,
    message: `Request failed with status ${response.status}.`,
  });
}

function parseValidationIssue(value: unknown): ValidationIssue[] {
  if (!isRecord(value)) return [];
  const location = value.loc;
  if (
    !Array.isArray(location) ||
    !location.every(
      (item) => typeof item === "string" || typeof item === "number",
    ) ||
    typeof value.msg !== "string" ||
    typeof value.type !== "string"
  ) {
    return [];
  }
  return [{ location, message: value.msg, type: value.type }];
}

function parseRetryAfter(value: string | null): number | undefined {
  if (value === null || !/^\d+$/.test(value)) return undefined;
  const seconds = Number(value);
  return Number.isSafeInteger(seconds) && seconds > 0 ? seconds : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
