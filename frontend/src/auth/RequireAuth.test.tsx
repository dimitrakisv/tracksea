import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import type { AuthApi } from "./api";
import { AuthProvider } from "./AuthProvider";
import { RequireAuth } from "./RequireAuth";
import type { UserResponse } from "./types";

const USER: UserResponse = {
  id: "4140da29-bd94-4c62-bd5f-79b1c61468e7",
  email: "observer@example.com",
  email_verified: true,
  display_name: "Marine Observer",
  authentication_methods: ["password"],
};

function apiWithStartup(getCurrentUser: AuthApi["getCurrentUser"]): AuthApi {
  return {
    getCsrfToken: vi.fn().mockResolvedValue("unused"),
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    getCurrentUser,
    updateProfile: vi.fn(),
    googleSignIn: vi.fn(),
    linkGoogle: vi.fn(),
  };
}

function Location() {
  return <span data-testid="location">{useLocation().pathname}</span>;
}

function renderGuard(api: AuthApi) {
  return render(
    <AuthProvider api={api}>
      <MemoryRouter initialEntries={["/protected"]}>
        <Location />
        <Routes>
          <Route path="/sign-in" element={<div>Sign-in destination</div>} />
          <Route
            path="/protected"
            element={
              <RequireAuth
                loadingFallback={<div>Loading session</div>}
                errorFallback={<div>Session unavailable</div>}
              >
                <div>Protected content</div>
              </RequireAuth>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe("RequireAuth", () => {
  it("fails closed with a loading fallback while startup is pending", () => {
    renderGuard(
      apiWithStartup(vi.fn().mockReturnValue(new Promise(() => undefined))),
    );

    expect(screen.getByText("Loading session")).toBeInTheDocument();
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/protected");
  });

  it("redirects only anonymous sessions to the fixed sign-in path", async () => {
    const required = new ApiError({
      status: 401,
      code: "authentication_required",
      message: "Authentication is required.",
    });
    renderGuard(apiWithStartup(vi.fn().mockRejectedValue(required)));

    await screen.findByText("Sign-in destination");
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/sign-in");
  });

  it("renders protected content for an authenticated user", async () => {
    renderGuard(apiWithStartup(vi.fn().mockResolvedValue(USER)));

    await screen.findByText("Protected content");
    expect(screen.getByTestId("location")).toHaveTextContent("/protected");
  });

  it("fails closed without redirecting when startup status is unknown", async () => {
    renderGuard(
      apiWithStartup(vi.fn().mockRejectedValue(new Error("network"))),
    );

    await waitFor(() =>
      expect(screen.getByText("Session unavailable")).toBeInTheDocument(),
    );
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
    expect(screen.queryByText("Sign-in destination")).not.toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/protected");
  });
});
