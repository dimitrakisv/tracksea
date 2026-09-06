import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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
import { GOOGLE_IDENTITY_SERVICES_URL } from "../auth/googleIdentityServices";
import type { AuthenticationMethod, UserResponse } from "../auth/types";

interface FakeGoogleAccountsId extends GoogleAccountsId {
  initialize: ReturnType<typeof vi.fn<GoogleAccountsId["initialize"]>>;
  renderButton: ReturnType<typeof vi.fn<GoogleAccountsId["renderButton"]>>;
}

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

async function renderProfile(
  user: UserResponse = TEST_USER,
  overrides: Parameters<typeof fakeAuthApi>[0] = {},
) {
  const api = fakeAuthApi({
    getCurrentUser: vi.fn().mockResolvedValue(user),
    ...overrides,
  });
  renderAuthApp(api, "/profile");
  await screen.findByRole("heading", { level: 1, name: "Profile" });
  return api;
}

function configureGoogle(): FakeGoogleAccountsId {
  clientSequence += 1;
  Object.assign(googleIdentityConfiguration, {
    status: "configured",
    clientId: `profile-${clientSequence}.apps.googleusercontent.com`,
  });
  const googleAccountsId: FakeGoogleAccountsId = {
    initialize: vi.fn<GoogleAccountsId["initialize"]>(),
    renderButton: vi.fn<GoogleAccountsId["renderButton"]>((host) => {
      const providerButton = document.createElement("iframe");
      providerButton.title = "Continue with Google";
      host.append(providerButton);
    }),
  };
  window.google = { accounts: { id: googleAccountsId } };
  return googleAccountsId;
}

async function googleCredentialCallback(
  googleAccountsId: FakeGoogleAccountsId,
) {
  await waitFor(() => expect(googleAccountsId.renderButton).toHaveBeenCalled());
  return googleAccountsId.initialize.mock.calls[0][0].callback;
}

describe("ProfilePage", () => {
  it("shows only safe account fields and keeps email read-only", async () => {
    await renderProfile();

    const account = screen.getByRole("heading", {
      name: "Account",
    }).parentElement!;
    expect(
      within(account).getByText(TEST_USER.display_name),
    ).toBeInTheDocument();
    expect(within(account).getByText(TEST_USER.email)).toBeInTheDocument();
    expect(within(account).getByText("Not verified")).toBeInTheDocument();
    expect(screen.getByText("Password")).toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("normalized_email");
    expect(document.body).not.toHaveTextContent("password hash");
    expect(document.body).not.toHaveTextContent("session token");
    expect(document.body).not.toHaveTextContent("Google subject");
    expect(document.body).not.toHaveTextContent("throttle");
  });

  it("submits the exact name once and adopts the server-normalized user", async () => {
    const operation = deferred<UserResponse>();
    const updateProfile = vi.fn().mockReturnValue(operation.promise);
    await renderProfile(TEST_USER, { updateProfile });
    const input = screen.getByRole("textbox", { name: "Display name" });
    const submittedName = "  Updated Observer  ";
    fireEvent.change(input, { target: { value: submittedName } });
    const form = screen
      .getByRole("button", { name: "Save display name" })
      .closest("form")!;

    fireEvent.submit(form);
    fireEvent.submit(form);

    expect(updateProfile).toHaveBeenCalledOnce();
    expect(updateProfile).toHaveBeenCalledWith({ display_name: submittedName });
    expect(form).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "Saving..." })).toBeDisabled();

    const updatedUser = { ...TEST_USER, display_name: "Updated Observer" };
    await act(async () => {
      operation.resolve(updatedUser);
      await operation.promise;
    });

    expect(input).toHaveValue("Updated Observer");
    expect(screen.getAllByText("Updated Observer")).toHaveLength(2);
    expect(screen.getByText("Profile updated.")).toHaveAttribute(
      "role",
      "status",
    );
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("maps display-name validation safely and preserves the signed-in user", async () => {
    const updateProfile = vi.fn().mockRejectedValue(
      new ApiError({
        status: 422,
        message: "private request body",
        validationIssues: [
          {
            location: ["body", "display_name"],
            message: "private validation detail",
            type: "value_error",
          },
        ],
      }),
    );
    await renderProfile(TEST_USER, { updateProfile });
    fireEvent.click(screen.getByRole("button", { name: "Save display name" }));

    const input = screen.getByRole("textbox", { name: "Display name" });
    await waitFor(() => expect(input).toHaveAttribute("aria-invalid", "true"));
    expect(input.getAttribute("aria-describedby")).toContain(
      "profile-display-name-error",
    );
    expect(
      document.getElementById("profile-display-name-error"),
    ).toHaveTextContent("Enter a display name between 1 and 80 characters.");
    expect(screen.getAllByText(TEST_USER.email)).toHaveLength(2);
    expect(document.body).not.toHaveTextContent("private request body");
    expect(document.body).not.toHaveTextContent("private validation detail");
  });

  it.each([
    [
      new ApiError({
        status: 403,
        code: "csrf_failed",
        message: "private CSRF detail",
      }),
      "The request could not be verified. Please try again.",
    ],
    [
      new Error("private network detail"),
      "Unable to update your profile. Please try again.",
    ],
  ])(
    "shows a safe update failure while preserving profile data",
    async (error, message) => {
      await renderProfile(TEST_USER, {
        updateProfile: vi.fn().mockRejectedValue(error),
      });

      fireEvent.click(
        screen.getByRole("button", { name: "Save display name" }),
      );

      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(screen.getAllByText(TEST_USER.email)).toHaveLength(2);
      expect(
        screen.getByRole("button", { name: "Save display name" }),
      ).toBeEnabled();
      expect(document.body).not.toHaveTextContent("private CSRF detail");
      expect(document.body).not.toHaveTextContent("private network detail");
    },
  );

  it("redirects and removes protected content after proven session loss", async () => {
    await renderProfile(TEST_USER, {
      updateProfile: vi.fn().mockRejectedValue(
        new ApiError({
          status: 401,
          code: "authentication_required",
          message: "private session detail",
        }),
      ),
    });

    fireEvent.click(screen.getByRole("button", { name: "Save display name" }));

    expect(
      await screen.findByRole("heading", { name: "Sign in to TrackSea" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Profile" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(TEST_USER.email)).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("private session detail");
  });

  it.each([
    [["password"] as AuthenticationMethod[], true],
    [["google"] as AuthenticationMethod[], false],
    [["password", "google"] as AuthenticationMethod[], false],
  ])(
    "uses authentication methods for Google-link eligibility",
    async (methods, eligible) => {
      await renderProfile({
        ...TEST_USER,
        email_verified: !eligible,
        authentication_methods: methods,
      });

      const linkHeading = screen.queryByRole("heading", {
        name: "Link Google",
      });
      if (eligible) expect(linkHeading).toBeInTheDocument();
      else expect(linkHeading).not.toBeInTheDocument();
    },
  );

  it("links Google with a fresh credential and adopts the returned methods", async () => {
    const googleAccountsId = configureGoogle();
    const linkedUser: UserResponse = {
      ...TEST_USER,
      authentication_methods: ["password", "google"],
    };
    const linkGoogle = vi.fn().mockResolvedValue(linkedUser);
    await renderProfile(TEST_USER, { linkGoogle });
    const callback = await googleCredentialCallback(googleAccountsId);

    act(() => callback({ credential: "fresh-profile-link-credential" }));

    await waitFor(() => expect(linkGoogle).toHaveBeenCalledOnce());
    expect(linkGoogle).toHaveBeenCalledWith({
      credential: "fresh-profile-link-credential",
    });
    expect(await screen.findByText("Google is now linked.")).toHaveAttribute(
      "role",
      "status",
    );
    expect(
      screen.queryByRole("heading", { name: "Link Google" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Google")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(
      "fresh-profile-link-credential",
    );
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it.each([
    [
      new ApiError({
        status: 409,
        code: "account_conflict",
        message: "private identity detail",
      }),
      "The Google account could not be linked.",
    ],
    [
      new ApiError({
        status: 401,
        code: "invalid_credentials",
        message: "private provider token",
      }),
      "Google account could not be verified.",
    ],
  ])("keeps profile linking failures generic", async (error, message) => {
    const googleAccountsId = configureGoogle();
    await renderProfile(TEST_USER, {
      linkGoogle: vi.fn().mockRejectedValue(error),
    });
    const callback = await googleCredentialCallback(googleAccountsId);

    act(() => callback({ credential: "private-link-candidate" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getAllByText(TEST_USER.email)).toHaveLength(2);
    expect(document.body).not.toHaveTextContent("private identity detail");
    expect(document.body).not.toHaveTextContent("private provider token");
    expect(document.body).not.toHaveTextContent("private-link-candidate");
  });

  it("keeps profile editing available when Google is not configured", async () => {
    await renderProfile();

    expect(
      screen.getByText(GOOGLE_IDENTITY_UNAVAILABLE_MESSAGE),
    ).toHaveAttribute("role", "status");
    expect(screen.getByRole("textbox", { name: "Display name" })).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Save display name" }),
    ).toBeEnabled();
    expect(
      document.querySelector(`script[src="${GOOGLE_IDENTITY_SERVICES_URL}"]`),
    ).toBeNull();
  });
});
