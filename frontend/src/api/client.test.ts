import { ApiError, createApiClient } from "./client";
import { describe, expect, it, vi } from "vitest";

function jsonResponse(
  body: unknown,
  status = 200,
  headers?: HeadersInit,
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("API fetch boundary", () => {
  it.each([
    ["GET", "/api/v1/auth/me"],
    ["GET", "/api/v1/auth/csrf"],
    ["POST", "/api/v1/auth/register"],
    ["POST", "/api/v1/auth/login"],
    ["POST", "/api/v1/auth/google"],
    ["POST", "/api/v1/auth/google/link"],
    ["POST", "/api/v1/auth/logout"],
    ["PATCH", "/api/v1/users/me"],
  ] as const)(
    "uses cookie credentials without bearer auth for %s %s",
    async (method, path) => {
      const fetcher = vi
        .fn<typeof fetch>()
        .mockResolvedValue(jsonResponse({ ok: true }));
      const client = createApiClient(fetcher);

      await client.request(path, { method });

      const [actualPath, init] = fetcher.mock.calls[0];
      expect(actualPath).toBe(path);
      expect(init?.method).toBe(method);
      expect(init?.credentials).toBe("include");
      expect(new Headers(init?.headers).has("Authorization")).toBe(false);
    },
  );

  it("uses relative paths, included credentials, JSON, and forwards cancellation", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse({ ok: true }));
    const signal = new AbortController().signal;
    const client = createApiClient(fetcher);

    await client.request("/api/v1/example", {
      method: "POST",
      body: { value: "safe" },
      signal,
    });

    expect(fetcher).toHaveBeenCalledOnce();
    const [path, init] = fetcher.mock.calls[0];
    expect(path).toBe("/api/v1/example");
    expect(init?.credentials).toBe("include");
    expect(init?.signal).toBe(signal);
    expect(init?.body).toBe('{"value":"safe"}');
    const headers = new Headers(init?.headers);
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.has("Authorization")).toBe(false);
  });

  it("supports 204 without attempting JSON parsing", async () => {
    const response = new Response(null, { status: 204 });
    const jsonSpy = vi.spyOn(response, "json");
    const client = createApiClient(
      vi.fn<typeof fetch>().mockResolvedValue(response),
    );

    await expect(
      client.request<void>("/api/v1/auth/logout"),
    ).resolves.toBeUndefined();
    expect(jsonSpy).not.toHaveBeenCalled();
  });

  it.each([
    "authentication_required",
    "invalid_credentials",
    "account_conflict",
    "account_link_required",
    "csrf_failed",
    "rate_limited",
  ] as const)("parses the %s auth error safely", async (code) => {
    const client = createApiClient(
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          jsonResponse(
            { detail: { code, message: "Safe server message." } },
            code === "rate_limited" ? 429 : 401,
            code === "rate_limited" ? { "Retry-After": "17" } : undefined,
          ),
        ),
    );

    const error = await client
      .request("/api/v1/auth/me")
      .catch((value: unknown) => value);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      code,
      message: "Safe server message.",
      retryAfterSeconds: code === "rate_limited" ? 17 : undefined,
    });
  });

  it("maps validation issues without retaining sensitive raw input", async () => {
    const candidate = "sensitive-candidate";
    const client = createApiClient(
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse(
          {
            detail: [
              {
                loc: ["body", "password"],
                msg: "Invalid value",
                type: "value_error",
                input: candidate,
              },
            ],
          },
          422,
        ),
      ),
    );

    const error = await client
      .request("/api/v1/auth/register")
      .catch((value: unknown) => value);

    expect(error).toBeInstanceOf(ApiError);
    if (!(error instanceof ApiError)) throw new Error("Expected ApiError.");
    expect(error.message).toBe("Request validation failed.");
    expect(error.validationIssues).toEqual([
      {
        location: ["body", "password"],
        message: "Invalid value",
        type: "value_error",
      },
    ]);
    expect(String(error)).not.toContain(candidate);
    expect(JSON.stringify(error)).not.toContain(candidate);
  });

  it("handles malformed error and success bodies without copying response data", async () => {
    const privateBody = "private-response-data";
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(privateBody, { status: 500 }))
      .mockResolvedValueOnce(new Response(privateBody, { status: 200 }));
    const client = createApiClient(fetcher);

    const serverError = await client
      .request("/api/first")
      .catch((value: unknown) => value);
    const protocolError = await client
      .request("/api/second")
      .catch((value: unknown) => value);

    expect(String(serverError)).toBe(
      "ApiError: Request failed with status 500.",
    );
    expect(String(protocolError)).toBe("ApiError: Unexpected server response.");
    expect(String(serverError)).not.toContain(privateBody);
    expect(String(protocolError)).not.toContain(privateBody);
  });

  it("maps network failures but preserves AbortError", async () => {
    const networkClient = createApiClient(
      vi
        .fn<typeof fetch>()
        .mockRejectedValue(new TypeError("private network detail")),
    );
    const abort = new DOMException("cancelled", "AbortError");
    const abortClient = createApiClient(
      vi.fn<typeof fetch>().mockRejectedValue(abort),
    );

    await expect(networkClient.request("/api/test")).rejects.toMatchObject({
      status: 0,
      message: "Network request failed.",
    });
    await expect(abortClient.request("/api/test")).rejects.toBe(abort);
  });
});
