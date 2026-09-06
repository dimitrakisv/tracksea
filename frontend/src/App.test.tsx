import { act, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  authenticationRequired,
  deferred,
  fakeAuthApi,
  renderAuthApp,
  TEST_USER,
} from "./test/authTestUtils";

describe("App routes", () => {
  it("redirects an anonymous root visit to sign-in", async () => {
    renderAuthApp(fakeAuthApi(), "/");

    expect(
      await screen.findByRole("heading", { name: "Sign in to TrackSea" }),
    ).toBeInTheDocument();
  });

  it("renders the protected root for an authenticated user", async () => {
    renderAuthApp(
      fakeAuthApi({
        getCurrentUser: vi.fn().mockResolvedValue(TEST_USER),
      }),
      "/",
    );

    expect(
      await screen.findByRole("heading", { level: 1, name: "TrackSea" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Technical foundation is running."),
    ).toBeInTheDocument();
  });

  it("does not expose protected content while startup is loading", () => {
    renderAuthApp(
      fakeAuthApi({
        getCurrentUser: vi.fn(
          () => new Promise<typeof TEST_USER>(() => undefined),
        ),
      }),
      "/",
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "Checking your session",
    );
    expect(
      screen.queryByText("Technical foundation is running."),
    ).not.toBeInTheDocument();
  });

  it("fails closed when protected-route startup fails", async () => {
    renderAuthApp(
      fakeAuthApi({
        getCurrentUser: vi.fn().mockRejectedValue(new Error("private detail")),
      }),
      "/",
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to determine the current session.",
    );
    expect(
      screen.queryByText("Technical foundation is running."),
    ).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("private detail");
  });

  it("keeps a delayed anonymous startup from exposing an auth form early", async () => {
    const startup = deferred<typeof TEST_USER>();
    const api = fakeAuthApi({
      getCurrentUser: vi.fn().mockReturnValue(startup.promise),
    });
    renderAuthApp(api, "/register");

    expect(
      screen.queryByRole("button", { name: "Create account" }),
    ).not.toBeInTheDocument();
    expect(api.register).not.toHaveBeenCalled();
    await act(() => {
      startup.reject(authenticationRequired());
      return startup.promise.catch(() => undefined);
    });
    expect(
      await screen.findByRole("heading", {
        name: "Create your TrackSea account",
      }),
    ).toBeInTheDocument();
  });
});
