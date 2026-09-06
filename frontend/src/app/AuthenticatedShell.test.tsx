import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  deferred,
  fakeAuthApi,
  renderAuthApp,
  TEST_USER,
} from "../test/authTestUtils";
import { appCopy } from "./copy";

async function renderAuthenticatedShell(
  overrides: Parameters<typeof fakeAuthApi>[0] = {},
) {
  const api = fakeAuthApi({
    getCurrentUser: vi.fn().mockResolvedValue(TEST_USER),
    ...overrides,
  });
  renderAuthApp(api, "/");
  await screen.findByRole("heading", { name: "Welcome to TrackSea" });
  return api;
}

describe("AuthenticatedShell", () => {
  it("renders canonical identity, safe user data, and primary navigation", async () => {
    await renderAuthenticatedShell();

    expect(screen.getByRole("link", { name: appCopy.name })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.getByText(appCopy.tagline)).toBeInTheDocument();
    expect(screen.getByText(TEST_USER.display_name)).toBeInTheDocument();
    expect(screen.getByText(TEST_USER.email)).toBeInTheDocument();
    const navigation = screen.getByRole("navigation", { name: "Primary" });
    expect(navigation).toBeVisible();
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Profile" })).toHaveAttribute(
      "href",
      "/profile",
    );
    expect(screen.getByRole("button", { name: "Sign out" })).toBeEnabled();
    expect(document.body).not.toHaveTextContent("normalized_email");
    expect(document.body).not.toHaveTextContent("password_hash");
    expect(document.body).not.toHaveTextContent("session token");
    expect(document.body).not.toHaveTextContent("Google subject");
    expect(document.body).not.toHaveTextContent("throttle");
  });

  it("shows the home placeholder without adding observation features", async () => {
    await renderAuthenticatedShell();

    expect(
      screen.getByText(
        /Observation capture is coming next\. TrackSea will let you record marine observations/,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    expect(screen.queryByText(/species search/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^map$/i)).not.toBeInTheDocument();
  });

  it("prevents duplicate logout and redirects only after success", async () => {
    const pending = deferred<void>();
    const logout = vi.fn().mockReturnValue(pending.promise);
    await renderAuthenticatedShell({ logout });
    const button = screen.getByRole("button", { name: "Sign out" });

    fireEvent.click(button);
    fireEvent.click(button);

    expect(logout).toHaveBeenCalledOnce();
    expect(
      screen.getByRole("button", { name: "Signing out..." }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Signing out..." }),
    ).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText(TEST_USER.email)).toBeInTheDocument();

    await act(async () => {
      pending.resolve(undefined);
      await pending.promise;
    });

    expect(
      await screen.findByRole("heading", { name: "Sign in to TrackSea" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(TEST_USER.email)).not.toBeInTheDocument();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("preserves the authenticated shell after logout failure and allows retry", async () => {
    const logout = vi
      .fn()
      .mockRejectedValue(new Error("private logout network detail"));
    await renderAuthenticatedShell({ logout });

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to sign out. Please try again.",
    );
    expect(screen.getByText(TEST_USER.email)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeEnabled();
    expect(document.body).not.toHaveTextContent(
      "private logout network detail",
    );

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(logout).toHaveBeenCalledTimes(2);
  });
});
