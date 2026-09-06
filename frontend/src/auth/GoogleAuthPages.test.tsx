import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import {
  GOOGLE_IDENTITY_UNAVAILABLE_MESSAGE,
  googleIdentityConfiguration,
} from "../config/googleIdentity";
import {
  authenticationRequired,
  deferred,
  fakeAuthApi,
  renderAuthApp,
  TEST_USER,
} from "../test/authTestUtils";
import type { UserResponse } from "./types";
import { useAuth } from "./useAuth";

interface FakeGoogleAccountsId extends GoogleAccountsId {
  initialize: ReturnType<typeof vi.fn<GoogleAccountsId["initialize"]>>;
  renderButton: ReturnType<typeof vi.fn<GoogleAccountsId["renderButton"]>>;
}

const LINKED_USER: UserResponse = {
  ...TEST_USER,
  authentication_methods: ["password", "google"],
};
let clientSequence = 0;

afterEach(() => {
  Object.assign(googleIdentityConfiguration, {
    status: "unconfigured",
    clientId: null,
    message: GOOGLE_IDENTITY_UNAVAILABLE_MESSAGE,
  });
  delete window.google;
  vi.restoreAllMocks();
});

function configureGoogle(): FakeGoogleAccountsId {
  clientSequence += 1;
  Object.assign(googleIdentityConfiguration, {
    status: "configured",
    clientId: `pages-${clientSequence}.apps.googleusercontent.com`,
  });
  const googleAccountsId: FakeGoogleAccountsId = {
    initialize: vi.fn<GoogleAccountsId["initialize"]>(),
    renderButton: vi.fn<GoogleAccountsId["renderButton"]>((host, options) => {
      const providerButton = document.createElement("iframe");
      providerButton.title = `Google ${options.text ?? "button"}`;
      host.append(providerButton);
    }),
  };
  window.google = { accounts: { id: googleAccountsId } };
  return googleAccountsId;
}

async function credentialCallback(googleAccountsId: FakeGoogleAccountsId) {
  await waitFor(() => expect(googleAccountsId.renderButton).toHaveBeenCalled());
  return googleAccountsId.initialize.mock.calls[0][0].callback;
}

function completePasswordSignIn() {
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "observer@example.com" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "fake password for linking" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

function LocationProbe() {
  const location = useLocation();
  return (
    <output data-testid="location-state">
      {JSON.stringify({ pathname: location.pathname, state: location.state })}
    </output>
  );
}

function AuthProbe() {
  const auth = useAuth();
  return (
    <output data-testid="auth-probe">
      {JSON.stringify({ status: auth.status, user: auth.user })}
    </output>
  );
}

describe("Google authentication pages", () => {
  it("does not initialize Google on registration until startup resolves", async () => {
    const googleAccountsId = configureGoogle();
    const startup = deferred<UserResponse>();
    renderAuthApp(
      fakeAuthApi({ getCurrentUser: vi.fn().mockReturnValue(startup.promise) }),
      "/register",
    );

    expect(googleAccountsId.initialize).not.toHaveBeenCalled();
    expect(screen.queryByTitle("Google signup_with")).not.toBeInTheDocument();

    startup.reject(authenticationRequired());
    expect(await screen.findByTitle("Google signup_with")).toBeInTheDocument();
    expect(googleAccountsId.initialize).toHaveBeenCalledOnce();
  });

  it("authenticates from registration and reaches the protected root", async () => {
    const googleAccountsId = configureGoogle();
    const googleSignIn = vi.fn().mockResolvedValue(TEST_USER);
    const api = fakeAuthApi({ googleSignIn });
    renderAuthApp(api, "/register", <AuthProbe />);
    const callback = await credentialCallback(googleAccountsId);

    act(() => callback({ credential: "registration-google-credential" }));

    expect(
      await screen.findByRole("heading", { name: "Welcome to TrackSea" }),
    ).toBeInTheDocument();
    expect(googleSignIn).toHaveBeenCalledWith({
      credential: "registration-google-credential",
    });
    expect(api.getCurrentUser).toHaveBeenCalledOnce();
    expect(screen.getByTestId("auth-probe")).toHaveTextContent(
      '"status":"authenticated"',
    );
    expect(screen.getByTestId("auth-probe")).not.toHaveTextContent(
      "registration-google-credential",
    );
  });

  it("guides a registration collision to sign-in with boolean-only state", async () => {
    const googleAccountsId = configureGoogle();
    const googleSignIn = vi.fn().mockRejectedValue(
      new ApiError({
        status: 409,
        code: "account_link_required",
        message: "private provider identity",
      }),
    );
    renderAuthApp(
      fakeAuthApi({ googleSignIn }),
      "/register",
      <LocationProbe />,
    );
    const callback = await credentialCallback(googleAccountsId);

    act(() => callback({ credential: "discarded-registration-credential" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "An existing TrackSea account uses this email.",
    );
    fireEvent.click(screen.getByRole("link", { name: "Sign in to continue" }));
    expect(
      await screen.findByRole("heading", { name: "Sign in to TrackSea" }),
    ).toBeInTheDocument();
    const state = screen.getByTestId("location-state").textContent ?? "";
    expect(state).toContain('"linkGoogleAfterPasswordSignIn":true');
    expect(state).not.toContain("discarded-registration-credential");
    expect(state).not.toContain("email");
    expect(state).not.toContain("subject");
    expect(document.body).not.toHaveTextContent("private provider identity");
  });

  it("renders sign-in Google auth without disturbing the password form", async () => {
    const googleAccountsId = configureGoogle();
    renderAuthApp(fakeAuthApi(), "/sign-in");

    expect(await screen.findByTitle("Google signin_with")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeEnabled();
    expect(screen.getByLabelText("Password")).toBeEnabled();
    expect(googleAccountsId.renderButton.mock.calls[0][1].text).toBe(
      "signin_with",
    );
  });

  it("authenticates from sign-in and reaches the protected root", async () => {
    const googleAccountsId = configureGoogle();
    const googleSignIn = vi.fn().mockResolvedValue(TEST_USER);
    renderAuthApp(fakeAuthApi({ googleSignIn }), "/sign-in");
    const callback = await credentialCallback(googleAccountsId);

    act(() => callback({ credential: "sign-in-google-credential" }));

    expect(
      await screen.findByRole("heading", { name: "Welcome to TrackSea" }),
    ).toBeInTheDocument();
    expect(googleSignIn).toHaveBeenCalledOnce();
  });

  it("uses a fresh second credential for explicit linking after password login", async () => {
    const googleAccountsId = configureGoogle();
    const firstCredential = "discarded-link-required-credential";
    const secondCredential = "fresh-explicit-link-credential";
    const googleSignIn = vi.fn().mockRejectedValue(
      new ApiError({
        status: 409,
        code: "account_link_required",
        message: "Link required.",
      }),
    );
    const login = vi.fn().mockResolvedValue(TEST_USER);
    const linkGoogle = vi.fn().mockResolvedValue(LINKED_USER);
    renderAuthApp(
      fakeAuthApi({ googleSignIn, login, linkGoogle }),
      "/sign-in",
      <AuthProbe />,
    );
    const callback = await credentialCallback(googleAccountsId);

    act(() => callback({ credential: firstCredential }));
    await screen.findByText(/If it is a password account/);
    expect(screen.getByLabelText("Password")).toBeEnabled();
    expect(linkGoogle).not.toHaveBeenCalled();

    completePasswordSignIn();
    expect(
      await screen.findByRole("heading", { name: "Link Google" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(googleAccountsId.renderButton).toHaveBeenCalledTimes(2),
    );
    expect(googleAccountsId.initialize).toHaveBeenCalledOnce();
    expect(googleAccountsId.renderButton.mock.calls[1][1].text).toBe(
      "continue_with",
    );

    act(() => callback({ credential: secondCredential }));
    expect(
      await screen.findByRole("heading", { name: "Welcome to TrackSea" }),
    ).toBeInTheDocument();
    expect(googleSignIn).toHaveBeenCalledWith({ credential: firstCredential });
    expect(linkGoogle).toHaveBeenCalledOnce();
    expect(linkGoogle).toHaveBeenCalledWith({ credential: secondCredential });
    expect(linkGoogle).not.toHaveBeenCalledWith({
      credential: firstCredential,
    });
    expect(screen.getByTestId("auth-probe")).toHaveTextContent(
      '"authentication_methods":["password","google"]',
    );
    expect(screen.getByTestId("auth-probe")).not.toHaveTextContent(
      firstCredential,
    );
    expect(screen.getByTestId("auth-probe")).not.toHaveTextContent(
      secondCredential,
    );
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("allows an authenticated user to continue without linking", async () => {
    const googleAccountsId = configureGoogle();
    const googleSignIn = vi.fn().mockRejectedValue(
      new ApiError({
        status: 409,
        code: "account_link_required",
        message: "Link required.",
      }),
    );
    const linkGoogle = vi.fn();
    renderAuthApp(fakeAuthApi({ googleSignIn, linkGoogle }), "/sign-in");
    const callback = await credentialCallback(googleAccountsId);
    act(() => callback({ credential: "discarded-before-skip" }));
    await screen.findByText(/If it is a password account/);

    completePasswordSignIn();
    const skip = await screen.findByRole("link", {
      name: "Continue without linking",
    });
    fireEvent.click(skip);

    expect(
      await screen.findByRole("heading", { name: "Welcome to TrackSea" }),
    ).toBeInTheDocument();
    expect(linkGoogle).not.toHaveBeenCalled();
  });

  it("returns safely to anonymous sign-in when linking proves session loss", async () => {
    const googleAccountsId = configureGoogle();
    const googleSignIn = vi.fn().mockRejectedValue(
      new ApiError({
        status: 409,
        code: "account_link_required",
        message: "Link required.",
      }),
    );
    const linkGoogle = vi.fn().mockRejectedValue(authenticationRequired());
    renderAuthApp(fakeAuthApi({ googleSignIn, linkGoogle }), "/sign-in");
    const callback = await credentialCallback(googleAccountsId);
    act(() => callback({ credential: "discarded-before-session-loss" }));
    await screen.findByText(/If it is a password account/);
    completePasswordSignIn();
    await screen.findByRole("heading", { name: "Link Google" });
    await waitFor(() =>
      expect(googleAccountsId.renderButton).toHaveBeenCalledTimes(2),
    );

    act(() => callback({ credential: "fresh-session-loss-credential" }));

    expect(
      await screen.findByRole("heading", { name: "Sign in to TrackSea" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeEnabled();
    expect(linkGoogle).toHaveBeenCalledOnce();
  });
});
