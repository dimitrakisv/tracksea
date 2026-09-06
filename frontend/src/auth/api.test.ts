import { ApiError, createApiClient } from "../api/client";
import { describe, expect, it, vi } from "vitest";
import { createAuthApi, type AuthApi } from "./api";
import type { UserResponse } from "./types";

const USER: UserResponse = {
  id: "4140da29-bd94-4c62-bd5f-79b1c61468e7",
  email: "observer@example.com",
  email_verified: true,
  display_name: "Marine Observer",
  authentication_methods: ["password", "google"],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function noContent(): Response {
  return new Response(null, { status: 204 });
}

function setup(responses: Response[]): {
  api: AuthApi;
  fetcher: ReturnType<typeof vi.fn<typeof fetch>>;
} {
  const fetcher = vi.fn<typeof fetch>();
  for (const response of responses) fetcher.mockResolvedValueOnce(response);
  return { api: createAuthApi(createApiClient(fetcher)), fetcher };
}

function requestAt(
  fetcher: ReturnType<typeof vi.fn<typeof fetch>>,
  index: number,
): [string, RequestInit] {
  const [path, init] = fetcher.mock.calls[index];
  return [String(path), init ?? {}];
}

describe("typed authentication API", () => {
  it("implements registration and login with transient passwords", async () => {
    const password = "private-password-candidate";
    const { api, fetcher } = setup([
      jsonResponse({ csrf_token: "csrf-one" }),
      jsonResponse(USER, 201),
      jsonResponse({ csrf_token: "csrf-two" }),
      jsonResponse(USER),
    ]);

    await expect(
      api.register({
        email: USER.email,
        password,
        display_name: USER.display_name,
      }),
    ).resolves.toEqual(USER);
    await expect(api.login({ email: USER.email, password })).resolves.toEqual(
      USER,
    );

    expect(requestAt(fetcher, 1)[0]).toBe("/api/v1/auth/register");
    expect(requestAt(fetcher, 3)[0]).toBe("/api/v1/auth/login");
    expect(requestAt(fetcher, 1)[1].body).toContain(password);
    expect(
      new Headers(requestAt(fetcher, 1)[1].headers).has("Authorization"),
    ).toBe(false);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("gets the current user once without CSRF bootstrap or 401 retry", async () => {
    const { api, fetcher } = setup([
      jsonResponse(
        {
          detail: {
            code: "authentication_required",
            message: "Authentication is required.",
          },
        },
        401,
      ),
    ]);

    await expect(api.getCurrentUser()).rejects.toMatchObject({
      code: "authentication_required",
      status: 401,
    });
    expect(fetcher).toHaveBeenCalledOnce();
    expect(requestAt(fetcher, 0)[0]).toBe("/api/v1/auth/me");
    expect(requestAt(fetcher, 0)[1].credentials).toBe("include");
  });

  it("sends profile and Google-link requests with one reusable CSRF token", async () => {
    const { api, fetcher } = setup([
      jsonResponse({ csrf_token: "shared-csrf" }),
      jsonResponse(USER),
      jsonResponse(USER),
    ]);

    await api.updateProfile({ display_name: "Updated Observer" });
    await api.linkGoogle({ credential: "transient-google-credential" });

    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(requestAt(fetcher, 0)[0]).toBe("/api/v1/auth/csrf");
    expect(requestAt(fetcher, 1)[0]).toBe("/api/v1/users/me");
    expect(requestAt(fetcher, 2)[0]).toBe("/api/v1/auth/google/link");
    expect(
      new Headers(requestAt(fetcher, 1)[1].headers).get("X-CSRF-Token"),
    ).toBe("shared-csrf");
    expect(
      new Headers(requestAt(fetcher, 2)[1].headers).get("X-CSRF-Token"),
    ).toBe("shared-csrf");
  });

  it("shares one in-flight CSRF bootstrap between concurrent unsafe calls", async () => {
    let releaseCsrf: ((response: Response) => void) | undefined;
    const csrfResponse = new Promise<Response>((resolve) => {
      releaseCsrf = resolve;
    });
    const fetcher = vi.fn<typeof fetch>((path) => {
      if (path === "/api/v1/auth/csrf") return csrfResponse;
      return Promise.resolve(jsonResponse(USER));
    });
    const api = createAuthApi(createApiClient(fetcher));

    const profile = api.updateProfile({ display_name: "Concurrent" });
    const link = api.linkGoogle({ credential: "concurrent-credential" });
    expect(fetcher).toHaveBeenCalledOnce();
    releaseCsrf?.(jsonResponse({ csrf_token: "one-token" }));

    await expect(Promise.all([profile, link])).resolves.toEqual([USER, USER]);
    expect(
      fetcher.mock.calls.filter(([path]) => path === "/api/v1/auth/csrf"),
    ).toHaveLength(1);
  });

  it.each(["register", "login", "googleSignIn", "logout"] as const)(
    "invalidates CSRF after successful %s",
    async (method) => {
      const operationResponse =
        method === "logout" ? noContent() : jsonResponse(USER);
      const { api, fetcher } = setup([
        jsonResponse({ csrf_token: "before-transition" }),
        operationResponse,
        jsonResponse({ csrf_token: "after-transition" }),
        jsonResponse(USER),
      ]);

      if (method === "register") {
        await api.register({
          email: USER.email,
          password: "password",
          display_name: "Name",
        });
      } else if (method === "login") {
        await api.login({ email: USER.email, password: "password" });
      } else if (method === "googleSignIn") {
        await api.googleSignIn({ credential: "credential" });
      } else {
        await expect(api.logout()).resolves.toBeUndefined();
      }
      await api.updateProfile({ display_name: "After transition" });

      expect(
        fetcher.mock.calls.filter(([path]) => path === "/api/v1/auth/csrf"),
      ).toHaveLength(2);
    },
  );

  it("invalidates on csrf_failed without replaying the request", async () => {
    const { api, fetcher } = setup([
      jsonResponse({ csrf_token: "stale" }),
      jsonResponse(
        {
          detail: {
            code: "csrf_failed",
            message: "Request could not be verified.",
          },
        },
        403,
      ),
      jsonResponse({ csrf_token: "fresh" }),
      jsonResponse(USER),
    ]);

    await expect(
      api.updateProfile({ display_name: "First" }),
    ).rejects.toMatchObject({
      code: "csrf_failed",
    });
    await expect(
      api.updateProfile({ display_name: "Second" }),
    ).resolves.toEqual(USER);
    expect(fetcher).toHaveBeenCalledTimes(4);
  });

  it("accepts Google sign-in 201 and safely types Google-link conflicts", async () => {
    const candidate = "google-candidate-not-for-errors";
    const { api, fetcher } = setup([
      jsonResponse({ csrf_token: "csrf" }),
      jsonResponse(USER, 201),
      jsonResponse({ csrf_token: "csrf-after-sign-in" }),
      jsonResponse(
        {
          detail: {
            code: "account_conflict",
            message: "The Google account could not be linked.",
          },
        },
        409,
      ),
    ]);

    await expect(api.googleSignIn({ credential: candidate })).resolves.toEqual(
      USER,
    );
    const error = await api
      .linkGoogle({ credential: candidate })
      .catch((value: unknown) => value);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "account_conflict", status: 409 });
    expect(String(error)).not.toContain(candidate);
    expect(requestAt(fetcher, 1)[0]).toBe("/api/v1/auth/google");
    expect(requestAt(fetcher, 3)[0]).toBe("/api/v1/auth/google/link");
  });

  it("exposes rate-limit delay and forwards AbortSignal", async () => {
    const response = jsonResponse(
      {
        detail: { code: "rate_limited", message: "Try again later." },
      },
      429,
    );
    response.headers.set("Retry-After", "21");
    const { api, fetcher } = setup([
      jsonResponse({ csrf_token: "csrf" }),
      response,
    ]);
    const signal = new AbortController().signal;

    await expect(
      api.login({ email: USER.email, password: "candidate" }, { signal }),
    ).rejects.toMatchObject({ code: "rate_limited", retryAfterSeconds: 21 });
    expect(requestAt(fetcher, 0)[1].signal).toBe(signal);
    expect(requestAt(fetcher, 1)[1].signal).toBe(signal);
  });

  it("never writes auth material to browser storage", async () => {
    const localSpy = vi.spyOn(window.localStorage, "setItem");
    const sessionSpy = vi.spyOn(window.sessionStorage, "setItem");
    const { api } = setup([
      jsonResponse({ csrf_token: "memory-only" }),
      jsonResponse(USER),
    ]);

    await api.login({ email: USER.email, password: "transient-password" });

    expect(localSpy).not.toHaveBeenCalled();
    expect(sessionSpy).not.toHaveBeenCalled();
  });
});
