import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import {
  authenticationRequired,
  deferred,
  fakeAuthApi,
  renderAuthApp,
  TEST_USER,
} from "../test/authTestUtils";

const PASSWORD = "fake sign in password";

async function renderSignIn(overrides: Parameters<typeof fakeAuthApi>[0] = {}) {
  const api = fakeAuthApi(overrides);
  renderAuthApp(api, "/sign-in");
  await screen.findByRole("heading", { name: "Sign in to TrackSea" });
  return api;
}

function completeSignInForm() {
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "Observer@Example.com" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: PASSWORD },
  });
}

describe("SignInPage", () => {
  it("renders accessible password-manager-compatible fields and navigation", async () => {
    await renderSignIn();

    const email = screen.getByLabelText("Email");
    const password = screen.getByLabelText("Password");
    expect(email).toHaveAttribute("type", "email");
    expect(email).toHaveAttribute("autocomplete", "username");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "current-password");
    expect(email).toBeRequired();
    expect(password).toBeRequired();
    expect(screen.getByRole("link", { name: "Create one" })).toHaveAttribute(
      "href",
      "/register",
    );
  });

  it("does not expose or submit the form while startup is loading", async () => {
    const startup = deferred<typeof TEST_USER>();
    const login = vi.fn();
    renderAuthApp(
      fakeAuthApi({
        getCurrentUser: vi.fn().mockReturnValue(startup.promise),
        login,
      }),
      "/sign-in",
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "Checking your session",
    );
    expect(
      screen.queryByRole("button", { name: "Sign in" }),
    ).not.toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();

    startup.reject(authenticationRequired());
    expect(
      await screen.findByRole("heading", { name: "Sign in to TrackSea" }),
    ).toBeInTheDocument();
  });

  it("submits exact credentials once, exposes busy state, and reaches protected root", async () => {
    const pending = deferred<typeof TEST_USER>();
    const login = vi.fn().mockReturnValue(pending.promise);
    await renderSignIn({ login });
    completeSignInForm();
    const form = screen
      .getByRole("button", { name: "Sign in" })
      .closest("form")!;

    fireEvent.submit(form);
    fireEvent.submit(form);

    expect(login).toHaveBeenCalledOnce();
    expect(login).toHaveBeenCalledWith({
      email: "Observer@Example.com",
      password: PASSWORD,
    });
    expect(form).toHaveAttribute("aria-busy", "true");
    expect(
      screen.getByRole("button", { name: "Signing in..." }),
    ).toBeDisabled();

    pending.resolve(TEST_USER);
    expect(
      await screen.findByRole("heading", { name: "Welcome to TrackSea" }),
    ).toBeInTheDocument();
    expect(JSON.stringify(TEST_USER)).not.toContain(PASSWORD);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("redirects authenticated startup and fails closed on startup error", async () => {
    const authenticated = renderAuthApp(
      fakeAuthApi({ getCurrentUser: vi.fn().mockResolvedValue(TEST_USER) }),
      "/sign-in",
    );
    expect(
      await screen.findByRole("heading", { name: "Welcome to TrackSea" }),
    ).toBeInTheDocument();
    authenticated.unmount();

    renderAuthApp(
      fakeAuthApi({
        getCurrentUser: vi.fn().mockRejectedValue(new Error("private startup")),
      }),
      "/sign-in",
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to determine the current session.",
    );
    expect(
      screen.queryByRole("button", { name: "Sign in" }),
    ).not.toBeInTheDocument();
  });

  it.each([
    [
      new ApiError({
        status: 401,
        code: "invalid_credentials",
        message: "private account method detail",
      }),
      "Email or password is incorrect.",
    ],
    [
      new ApiError({
        status: 429,
        code: "rate_limited",
        message: "private throttle detail",
        retryAfterSeconds: 21,
      }),
      "Too many sign-in attempts. Try again in approximately 21 seconds.",
    ],
    [
      new ApiError({
        status: 403,
        code: "csrf_failed",
        message: "private CSRF",
      }),
      "The request could not be verified. Please try again.",
    ],
    [
      new Error("private network detail"),
      "Unable to complete the request. Please try again.",
    ],
  ])(
    "shows a safe local failure and permits a deliberate retry",
    async (error, message) => {
      const login = vi.fn().mockRejectedValue(error);
      await renderSignIn({ login });
      completeSignInForm();
      fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(login).toHaveBeenCalledOnce();
      expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
      expect(document.body).not.toHaveTextContent(
        "private account method detail",
      );
      expect(document.body).not.toHaveTextContent("private throttle detail");
      expect(document.body).not.toHaveTextContent("Try Google");
    },
  );
});
