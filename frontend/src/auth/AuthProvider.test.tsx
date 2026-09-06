import { act, render, screen, waitFor } from "@testing-library/react";
import { StrictMode, useEffect } from "react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import type { AuthApi } from "./api";
import { AuthProvider } from "./AuthProvider";
import type { AuthContextValue } from "./context";
import type { UserResponse } from "./types";
import { useAuth } from "./useAuth";

const USER: UserResponse = {
  id: "4140da29-bd94-4c62-bd5f-79b1c61468e7",
  email: "observer@example.com",
  email_verified: true,
  display_name: "Marine Observer",
  authentication_methods: ["password"],
};
const LINKED_USER: UserResponse = {
  ...USER,
  authentication_methods: ["password", "google"],
};

function fakeApi(overrides: Partial<AuthApi> = {}): AuthApi {
  return {
    getCsrfToken: vi.fn().mockResolvedValue("unused"),
    register: vi.fn().mockResolvedValue(USER),
    login: vi.fn().mockResolvedValue(USER),
    logout: vi.fn().mockResolvedValue(undefined),
    getCurrentUser: vi.fn().mockResolvedValue(USER),
    updateProfile: vi.fn().mockResolvedValue(USER),
    googleSignIn: vi.fn().mockResolvedValue(USER),
    linkGoogle: vi.fn().mockResolvedValue(LINKED_USER),
    ...overrides,
  };
}

function authenticationRequired(): ApiError {
  return new ApiError({
    status: 401,
    code: "authentication_required",
    message: "Authentication is required.",
  });
}

function deferred<T>(): {
  promise: Promise<T>;
  resolve(value: T): void;
} {
  let resolvePromise: ((value: T) => void) | undefined;
  const promise = new Promise<T>((resolve) => {
    resolvePromise = resolve;
  });
  return {
    promise,
    resolve(value) {
      resolvePromise?.(value);
    },
  };
}

let currentAuth: AuthContextValue | undefined;

function Probe() {
  const auth = useAuth();
  useEffect(() => {
    currentAuth = auth;
  }, [auth]);
  return (
    <div>
      <span data-testid="status">{auth.status}</span>
      <span data-testid="user">{auth.user?.display_name ?? "none"}</span>
      <span data-testid="error">{auth.error?.message ?? "none"}</span>
    </div>
  );
}

describe("AuthProvider", () => {
  it("starts loading and resolves an authenticated current user", async () => {
    const startup = deferred<UserResponse>();
    const api = fakeApi({
      getCurrentUser: vi.fn().mockReturnValue(startup.promise),
    });

    render(
      <AuthProvider api={api}>
        <Probe />
      </AuthProvider>,
    );

    expect(screen.getByTestId("status")).toHaveTextContent("loading");
    expect(screen.getByTestId("user")).toHaveTextContent("none");
    startup.resolve(USER);
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated"),
    );
    expect(screen.getByTestId("user")).toHaveTextContent("Marine Observer");
    expect(api.getCurrentUser).toHaveBeenCalledOnce();
    expect(api.getCsrfToken).not.toHaveBeenCalled();
  });

  it("maps only authentication_required startup failures to anonymous", async () => {
    const api = fakeApi({
      getCurrentUser: vi.fn().mockRejectedValue(authenticationRequired()),
    });

    render(
      <AuthProvider api={api}>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("anonymous"),
    );
    expect(screen.getByTestId("error")).toHaveTextContent("none");
    expect(api.getCurrentUser).toHaveBeenCalledOnce();
  });

  it("maps other startup failures to a safe fail-closed error", async () => {
    const privateDetail = "private transport diagnostics";
    const api = fakeApi({
      getCurrentUser: vi.fn().mockRejectedValue(new Error(privateDetail)),
    });

    render(
      <AuthProvider api={api}>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("error"),
    );
    expect(screen.getByTestId("user")).toHaveTextContent("none");
    expect(screen.getByTestId("error")).toHaveTextContent(
      "Unable to determine the current session.",
    );
    expect(document.body).not.toHaveTextContent(privateDetail);
    expect(api.getCurrentUser).toHaveBeenCalledOnce();
  });

  it("shares one delayed startup request through StrictMode remounting", async () => {
    const startup = deferred<UserResponse>();
    const getCurrentUser = vi.fn().mockReturnValue(startup.promise);
    const api = fakeApi({ getCurrentUser });

    render(
      <StrictMode>
        <AuthProvider api={api}>
          <Probe />
        </AuthProvider>
      </StrictMode>,
    );

    expect(getCurrentUser).toHaveBeenCalledOnce();
    startup.resolve(USER);
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated"),
    );
    expect(getCurrentUser).toHaveBeenCalledOnce();
  });

  it("synchronizes registration, login, and Google sign-in successes", async () => {
    const registered = { ...USER, display_name: "Registered" };
    const loggedIn = { ...USER, display_name: "Logged In" };
    const googleUser = { ...LINKED_USER, display_name: "Google User" };
    const api = fakeApi({
      getCurrentUser: vi.fn().mockRejectedValue(authenticationRequired()),
      register: vi.fn().mockResolvedValue(registered),
      login: vi.fn().mockResolvedValue(loggedIn),
      googleSignIn: vi.fn().mockResolvedValue(googleUser),
    });
    const password = "transient-password";
    const credential = "transient-google-credential";
    render(
      <AuthProvider api={api}>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(currentAuth?.status).toBe("anonymous"));

    await act(() =>
      currentAuth!.register({
        email: USER.email,
        password,
        display_name: "Registered",
      }),
    );
    expect(currentAuth?.user).toEqual(registered);
    await act(() => currentAuth!.login({ email: USER.email, password }));
    expect(currentAuth?.user).toEqual(loggedIn);
    await act(() => currentAuth!.googleSignIn({ credential }));
    expect(currentAuth?.user).toEqual(googleUser);
    expect(JSON.stringify(currentAuth)).not.toContain(password);
    expect(JSON.stringify(currentAuth)).not.toContain(credential);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("replaces the authoritative user after profile update and Google linking", async () => {
    const updated = { ...USER, display_name: "Updated" };
    const api = fakeApi({
      updateProfile: vi.fn().mockResolvedValue(updated),
      linkGoogle: vi.fn().mockResolvedValue(LINKED_USER),
    });
    render(
      <AuthProvider api={api}>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(currentAuth?.status).toBe("authenticated"));

    await act(() => currentAuth!.updateProfile({ display_name: "Updated" }));
    expect(currentAuth?.user).toEqual(updated);
    await act(() => currentAuth!.linkGoogle({ credential: "transient" }));
    expect(currentAuth?.user).toEqual(LINKED_USER);
  });

  it("surfaces invalid login without turning anonymous state into an error", async () => {
    const invalid = new ApiError({
      status: 401,
      code: "invalid_credentials",
      message: "Email or password is incorrect.",
    });
    const api = fakeApi({
      getCurrentUser: vi.fn().mockRejectedValue(authenticationRequired()),
      login: vi.fn().mockRejectedValue(invalid),
    });
    render(
      <AuthProvider api={api}>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(currentAuth?.status).toBe("anonymous"));

    await expect(
      currentAuth!.login({ email: USER.email, password: "transient-password" }),
    ).rejects.toBe(invalid);
    expect(currentAuth?.status).toBe("anonymous");
    expect(currentAuth?.error).toBeNull();
  });

  it("preserves authenticated state for ordinary action failures", async () => {
    const validation = new ApiError({
      status: 422,
      message: "Request validation failed.",
    });
    const conflict = new ApiError({
      status: 409,
      code: "account_conflict",
      message: "The Google account could not be linked.",
    });
    const logoutFailure = new ApiError({
      status: 500,
      message: "Request failed.",
    });
    const api = fakeApi({
      updateProfile: vi.fn().mockRejectedValue(validation),
      linkGoogle: vi.fn().mockRejectedValue(conflict),
      logout: vi.fn().mockRejectedValue(logoutFailure),
    });
    render(
      <AuthProvider api={api}>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(currentAuth?.status).toBe("authenticated"));

    await expect(
      currentAuth!.updateProfile({ display_name: "Invalid" }),
    ).rejects.toBe(validation);
    expect(currentAuth?.user).toEqual(USER);
    await expect(
      currentAuth!.linkGoogle({ credential: "invalid" }),
    ).rejects.toBe(conflict);
    expect(currentAuth?.user).toEqual(USER);
    await expect(currentAuth!.logout()).rejects.toBe(logoutFailure);
    expect(currentAuth?.user).toEqual(USER);
  });

  it.each(["updateProfile", "linkGoogle"] as const)(
    "clears stale user when %s proves session loss",
    async (method) => {
      const api = fakeApi({
        [method]: vi.fn().mockRejectedValue(authenticationRequired()),
      });
      render(
        <AuthProvider api={api}>
          <Probe />
        </AuthProvider>,
      );
      await waitFor(() => expect(currentAuth?.status).toBe("authenticated"));

      const operation =
        method === "updateProfile"
          ? currentAuth!.updateProfile({ display_name: "Update" })
          : currentAuth!.linkGoogle({ credential: "credential" });
      await act(async () => {
        await expect(operation).rejects.toMatchObject({
          code: "authentication_required",
        });
      });
      expect(currentAuth?.status).toBe("anonymous");
      expect(currentAuth?.user).toBeNull();
    },
  );

  it("becomes anonymous only after logout succeeds", async () => {
    const logout = deferred<void>();
    const api = fakeApi({ logout: vi.fn().mockReturnValue(logout.promise) });
    render(
      <AuthProvider api={api}>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(currentAuth?.status).toBe("authenticated"));

    const operation = currentAuth!.logout();
    expect(currentAuth?.status).toBe("authenticated");
    logout.resolve(undefined);
    await act(() => operation);
    expect(currentAuth?.status).toBe("anonymous");
    expect(currentAuth?.user).toBeNull();
  });

  it("fails clearly when useAuth is outside the provider", () => {
    expect(() => render(<Probe />)).toThrow(
      "useAuth must be used within an AuthProvider.",
    );
  });
});
