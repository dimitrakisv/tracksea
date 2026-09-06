import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "../api/client";
import { renderAuthApp } from "../test/authTestUtils";
import { createAuthApi } from "./api";
import type { UserResponse } from "./types";

const REGISTERED_USER: UserResponse = {
  id: "82185b22-c2f6-4ef7-b588-e5560e716f73",
  email: "observer@example.com",
  email_verified: false,
  display_name: "Marine Observer",
  authentication_methods: ["password"],
};

const PASSWORD = "integration-only-password";

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

function authError(
  status: number,
  code: "authentication_required" | "invalid_credentials" | "rate_limited",
  headers?: HeadersInit,
): Response {
  return jsonResponse(
    { detail: { code, message: "Safe authentication error." } },
    status,
    headers,
  );
}

function requestAt(
  fetcher: ReturnType<typeof vi.fn<typeof fetch>>,
  index: number,
): [string, RequestInit] {
  const [path, init] = fetcher.mock.calls[index];
  return [String(path), init ?? {}];
}

function expectCookieRequest(
  fetcher: ReturnType<typeof vi.fn<typeof fetch>>,
  index: number,
  path: string,
  method: "POST" | "PATCH",
  csrfToken: string,
  body?: unknown,
): void {
  const [actualPath, init] = requestAt(fetcher, index);
  const headers = new Headers(init.headers);

  expect(actualPath).toBe(path);
  expect(actualPath).not.toMatch(/^https?:\/\//);
  expect(init.credentials).toBe("include");
  expect(init.method).toBe(method);
  expect(headers.get("X-CSRF-Token")).toBe(csrfToken);
  expect(headers.has("Authorization")).toBe(false);
  if (body === undefined) {
    expect(init.body).toBeUndefined();
    expect(headers.has("Content-Type")).toBe(false);
  } else {
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init.body))).toEqual(body);
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

describe("authentication workflow integration", () => {
  it("composes registration, profile update, and logout through the real client", async () => {
    const updatedUser = {
      ...REGISTERED_USER,
      display_name: "Normalized Observer",
    };
    let csrfRequestCount = 0;
    const logoutResponse = new Response(null, { status: 204 });
    const logoutJson = vi.spyOn(logoutResponse, "json");
    const fetcher = vi.fn<typeof fetch>(async (path, init) => {
      const request = `${init?.method ?? "GET"} ${String(path)}`;
      if (request === "GET /api/v1/auth/me") {
        return authError(401, "authentication_required");
      }
      if (request === "GET /api/v1/auth/csrf") {
        csrfRequestCount += 1;
        return jsonResponse({
          csrf_token: csrfRequestCount === 1 ? "register-csrf" : "profile-csrf",
        });
      }
      if (request === "POST /api/v1/auth/register") {
        return jsonResponse(REGISTERED_USER, 201);
      }
      if (request === "PATCH /api/v1/users/me") {
        return jsonResponse(updatedUser);
      }
      if (request === "POST /api/v1/auth/logout") return logoutResponse;
      throw new Error(`Unexpected test request: ${request}`);
    });
    vi.stubGlobal("fetch", fetcher);
    renderAuthApp(createAuthApi(createApiClient()), "/register");

    expect(
      await screen.findByRole("heading", {
        name: "Create your TrackSea account",
      }),
    ).toBeInTheDocument();
    expect(requestAt(fetcher, 0)[0]).toBe("/api/v1/auth/me");
    expect(requestAt(fetcher, 0)[1].credentials).toBe("include");
    expect(fetcher).toHaveBeenCalledOnce();

    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: REGISTERED_USER.display_name },
    });
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: REGISTERED_USER.email },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: PASSWORD },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(
      await screen.findByRole("heading", { name: "Welcome to TrackSea" }),
    ).toBeInTheDocument();
    expectCookieRequest(
      fetcher,
      2,
      "/api/v1/auth/register",
      "POST",
      "register-csrf",
      {
        display_name: REGISTERED_USER.display_name,
        email: REGISTERED_USER.email,
        password: PASSWORD,
      },
    );
    expect(
      Object.keys(JSON.parse(String(requestAt(fetcher, 2)[1].body))),
    ).toEqual(["display_name", "email", "password"]);

    fireEvent.click(screen.getByRole("link", { name: "Profile" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Profile" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Display name" }), {
      target: { value: "  Normalized Observer  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save display name" }));

    expect(await screen.findByText("Profile updated.")).toBeInTheDocument();
    expect(screen.getAllByText("Normalized Observer")).toHaveLength(2);
    expectCookieRequest(
      fetcher,
      4,
      "/api/v1/users/me",
      "PATCH",
      "profile-csrf",
      { display_name: "  Normalized Observer  " },
    );

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(
      await screen.findByRole("heading", { name: "Sign in to TrackSea" }),
    ).toBeInTheDocument();
    expectCookieRequest(
      fetcher,
      5,
      "/api/v1/auth/logout",
      "POST",
      "profile-csrf",
    );
    expect(csrfRequestCount).toBe(2);
    expect(logoutJson).not.toHaveBeenCalled();
    expect(screen.queryByText("Normalized Observer")).not.toBeInTheDocument();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("carries safe login failures through to the UI before authenticating", async () => {
    let loginAttempt = 0;
    const fetcher = vi.fn<typeof fetch>(async (path, init) => {
      const request = `${init?.method ?? "GET"} ${String(path)}`;
      if (request === "GET /api/v1/auth/me") {
        return authError(401, "authentication_required");
      }
      if (request === "GET /api/v1/auth/csrf") {
        return jsonResponse({ csrf_token: "login-csrf" });
      }
      if (request === "POST /api/v1/auth/login") {
        loginAttempt += 1;
        if (loginAttempt === 1) return authError(401, "invalid_credentials");
        if (loginAttempt === 2) {
          return authError(429, "rate_limited", { "Retry-After": "21" });
        }
        return jsonResponse(REGISTERED_USER);
      }
      throw new Error(`Unexpected test request: ${request}`);
    });
    vi.stubGlobal("fetch", fetcher);
    renderAuthApp(createAuthApi(createApiClient()), "/sign-in");

    expect(
      await screen.findByRole("heading", { name: "Sign in to TrackSea" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: REGISTERED_USER.email },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: PASSWORD },
    });

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Email or password is incorrect.",
    );
    expect(document.body).not.toHaveTextContent("account exists");
    expect(document.body).not.toHaveTextContent("password account");
    expect(document.body).not.toHaveTextContent(PASSWORD);

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many sign-in attempts. Try again in approximately 21 seconds.",
    );

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(
      await screen.findByRole("heading", { name: "Welcome to TrackSea" }),
    ).toBeInTheDocument();
    expect(
      fetcher.mock.calls.filter(([path]) => path === "/api/v1/auth/csrf"),
    ).toHaveLength(1);
    for (const index of [2, 3, 4]) {
      expectCookieRequest(
        fetcher,
        index,
        "/api/v1/auth/login",
        "POST",
        "login-csrf",
        { email: REGISTERED_USER.email, password: PASSWORD },
      );
      expect(
        Object.keys(JSON.parse(String(requestAt(fetcher, index)[1].body))),
      ).toEqual(["email", "password"]);
    }
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
