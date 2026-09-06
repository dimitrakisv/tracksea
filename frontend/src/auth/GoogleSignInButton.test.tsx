import { act, render, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import {
  GOOGLE_IDENTITY_UNAVAILABLE_MESSAGE,
  googleIdentityConfiguration,
} from "../config/googleIdentity";
import {
  deferred,
  fakeAuthApi,
  renderAuthApp,
  TEST_USER,
} from "../test/authTestUtils";
import type { AuthApi } from "./api";
import { AuthProvider } from "./AuthProvider";
import { GOOGLE_IDENTITY_SERVICES_URL } from "./googleIdentityServices";
import { GoogleSignInButton } from "./GoogleSignInButton";

interface FakeGoogleAccountsId extends GoogleAccountsId {
  initialize: ReturnType<typeof vi.fn<GoogleAccountsId["initialize"]>>;
  renderButton: ReturnType<typeof vi.fn<GoogleAccountsId["renderButton"]>>;
  prompt: ReturnType<typeof vi.fn>;
}

let clientSequence = 0;

afterEach(() => {
  setUnconfigured();
  delete window.google;
  document.head.replaceChildren();
  vi.restoreAllMocks();
});

function configureGoogle(): FakeGoogleAccountsId {
  clientSequence += 1;
  Object.assign(googleIdentityConfiguration, {
    status: "configured",
    clientId: `component-${clientSequence}.apps.googleusercontent.com`,
  });
  const googleAccountsId: FakeGoogleAccountsId = {
    initialize: vi.fn<GoogleAccountsId["initialize"]>(),
    renderButton: vi.fn<GoogleAccountsId["renderButton"]>((host) => {
      const providerButton = document.createElement("iframe");
      providerButton.title = "Continue with Google";
      host.append(providerButton);
    }),
    prompt: vi.fn(),
  };
  window.google = { accounts: { id: googleAccountsId } };
  return googleAccountsId;
}

function setUnconfigured() {
  Object.assign(googleIdentityConfiguration, {
    status: "unconfigured",
    clientId: null,
    message: GOOGLE_IDENTITY_UNAVAILABLE_MESSAGE,
  });
}

function renderButton(
  api: AuthApi,
  googleAccountsId: FakeGoogleAccountsId,
  mode: "authenticate" | "link" = "authenticate",
) {
  const onSuccess = vi.fn();
  const onAccountLinkRequired = vi.fn();
  const result = render(
    <StrictMode>
      <MemoryRouter>
        <AuthProvider api={api}>
          <GoogleSignInButton
            mode={mode}
            buttonText={mode === "link" ? "continue_with" : "signin_with"}
            onSuccess={onSuccess}
            onAccountLinkRequired={onAccountLinkRequired}
          />
        </AuthProvider>
      </MemoryRouter>
    </StrictMode>,
  );
  return { ...result, googleAccountsId, onSuccess, onAccountLinkRequired };
}

async function initializedCallback(googleAccountsId: FakeGoogleAccountsId) {
  await waitFor(() =>
    expect(googleAccountsId.renderButton).toHaveBeenCalledOnce(),
  );
  return googleAccountsId.initialize.mock.calls[0][0].callback;
}

describe("GoogleSignInButton", () => {
  it("renders the official button and initializes only once under StrictMode", async () => {
    const googleAccountsId = configureGoogle();
    renderButton(fakeAuthApi(), googleAccountsId);

    await initializedCallback(googleAccountsId);
    expect(googleAccountsId.initialize).toHaveBeenCalledOnce();
    expect(googleAccountsId.initialize.mock.calls[0][0]).toMatchObject({
      client_id: googleIdentityConfiguration.clientId,
      auto_select: false,
    });
    const [host, options] = googleAccountsId.renderButton.mock.calls[0];
    expect(host).toBeInstanceOf(HTMLElement);
    expect(options).toEqual({
      type: "standard",
      theme: "outline",
      size: "large",
      text: "signin_with",
      shape: "rectangular",
      logo_alignment: "left",
    });
    expect(within(host).getByTitle("Continue with Google")).toBeInTheDocument();
    expect(googleAccountsId.prompt).not.toHaveBeenCalled();
  });

  it("submits one transient credential while busy and reports success", async () => {
    const googleAccountsId = configureGoogle();
    const operation = deferred<typeof TEST_USER>();
    const googleSignIn = vi.fn().mockReturnValue(operation.promise);
    const localWrite = vi.spyOn(Storage.prototype, "setItem");
    const view = renderButton(fakeAuthApi({ googleSignIn }), googleAccountsId);
    const callback = await initializedCallback(googleAccountsId);

    act(() => {
      callback({ credential: "first-transient-google-credential" });
      callback({ credential: "duplicate-transient-google-credential" });
    });

    expect(googleSignIn).toHaveBeenCalledOnce();
    expect(googleSignIn).toHaveBeenCalledWith({
      credential: "first-transient-google-credential",
    });
    expect(screen.getByRole("status")).toHaveTextContent(
      "Completing Google sign-in",
    );

    await act(async () => {
      operation.resolve(TEST_USER);
      await operation.promise;
    });
    expect(view.onSuccess).toHaveBeenCalledWith(TEST_USER);
    expect(document.body).not.toHaveTextContent(
      "first-transient-google-credential",
    );
    expect(localWrite).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it.each([
    [
      "authenticate" as const,
      new ApiError({
        status: 401,
        code: "invalid_credentials",
        message: "private provider detail",
      }),
      "Google sign-in could not be completed.",
    ],
    [
      "authenticate" as const,
      new ApiError({
        status: 403,
        code: "csrf_failed",
        message: "private CSRF detail",
      }),
      "The request could not be verified. Please try again.",
    ],
    [
      "authenticate" as const,
      new Error("private network detail"),
      "Unable to complete Google sign-in. Please try again.",
    ],
    [
      "link" as const,
      new ApiError({
        status: 409,
        code: "account_conflict",
        message: "private identity detail",
      }),
      "The Google account could not be linked.",
    ],
    [
      "link" as const,
      new ApiError({
        status: 401,
        code: "invalid_credentials",
        message: "private token detail",
      }),
      "Google account could not be verified.",
    ],
  ])(
    "maps %s failures to safe accessible copy",
    async (mode, error, message) => {
      const googleAccountsId = configureGoogle();
      const operation = vi.fn().mockRejectedValue(error);
      const api =
        mode === "authenticate"
          ? fakeAuthApi({ googleSignIn: operation })
          : fakeAuthApi({ linkGoogle: operation });
      renderButton(api, googleAccountsId, mode);
      const callback = await initializedCallback(googleAccountsId);

      act(() => callback({ credential: "private-candidate" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(operation).toHaveBeenCalledOnce();
      expect(document.body).not.toHaveTextContent("private-candidate");
      expect(document.body).not.toHaveTextContent("private provider detail");
      expect(document.body).not.toHaveTextContent("private identity detail");
    },
  );

  it("uses the account-link-required callback without retaining the credential", async () => {
    const googleAccountsId = configureGoogle();
    const googleSignIn = vi.fn().mockRejectedValue(
      new ApiError({
        status: 409,
        code: "account_link_required",
        message: "private collision detail",
      }),
    );
    const view = renderButton(fakeAuthApi({ googleSignIn }), googleAccountsId);
    const callback = await initializedCallback(googleAccountsId);

    act(() => callback({ credential: "discarded-collision-credential" }));

    await waitFor(() =>
      expect(view.onAccountLinkRequired).toHaveBeenCalledOnce(),
    );
    expect(view.onSuccess).not.toHaveBeenCalled();
    expect(document.body).not.toHaveTextContent(
      "discarded-collision-credential",
    );
  });

  it("clears its host and ignores credentials after unmount", async () => {
    const googleAccountsId = configureGoogle();
    const api = fakeAuthApi();
    const view = renderButton(api, googleAccountsId);
    const callback = await initializedCallback(googleAccountsId);
    const host = googleAccountsId.renderButton.mock.calls[0][0];
    expect(host.childElementCount).toBe(1);

    view.unmount();
    expect(host.childElementCount).toBe(0);
    act(() => callback({ credential: "late-unmounted-credential" }));
    expect(api.googleSignIn).not.toHaveBeenCalled();
  });

  it("leaves password registration usable when configuration is absent", async () => {
    setUnconfigured();
    renderAuthApp(fakeAuthApi(), "/register");

    expect(
      await screen.findByText("Google sign-in is not configured."),
    ).toHaveAttribute("role", "status");
    expect(screen.getByLabelText("Password")).toBeEnabled();
    expect(
      document.querySelector(`script[src="${GOOGLE_IDENTITY_SERVICES_URL}"]`),
    ).toBeNull();
  });

  it("leaves password registration usable after official script failure", async () => {
    configureGoogle();
    delete window.google;
    renderAuthApp(fakeAuthApi(), "/register");
    await screen.findByRole("heading", {
      name: "Create your TrackSea account",
    });
    const script = document.querySelector<HTMLScriptElement>(
      `script[src="${GOOGLE_IDENTITY_SERVICES_URL}"]`,
    );
    expect(script).not.toBeNull();

    act(() => script?.dispatchEvent(new Event("error")));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Google sign-in could not be loaded. You can still use email and password.",
    );
    expect(screen.getByLabelText("Password")).toBeEnabled();
  });
});
