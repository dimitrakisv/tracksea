import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import {
  deferred,
  fakeAuthApi,
  renderAuthApp,
  TEST_USER,
} from "../test/authTestUtils";

const PASSWORD = "fake password value 123";

async function renderRegistration(
  overrides: Parameters<typeof fakeAuthApi>[0] = {},
) {
  const api = fakeAuthApi(overrides);
  renderAuthApp(api, "/register");
  await screen.findByRole("heading", { name: "Create your TrackSea account" });
  return api;
}

function completeRegistrationForm() {
  fireEvent.change(screen.getByLabelText("Display name"), {
    target: { value: "  Sea Observer  " },
  });
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "Observer@Example.com" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: PASSWORD },
  });
}

describe("RegisterPage", () => {
  it("renders accessible password-manager-compatible fields and guidance", async () => {
    await renderRegistration();

    const displayName = screen.getByLabelText("Display name");
    const email = screen.getByLabelText("Email");
    const password = screen.getByLabelText("Password");
    expect(displayName).toHaveAttribute("name", "display_name");
    expect(displayName).toHaveAttribute("autocomplete", "name");
    expect(email).toHaveAttribute("type", "email");
    expect(email).toHaveAttribute("autocomplete", "email");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "new-password");
    expect(displayName).toBeRequired();
    expect(email).toBeRequired();
    expect(password).toBeRequired();
    expect(screen.getByText(/Use at least 15 characters/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      "/sign-in",
    );
  });

  it("submits exact values once, exposes busy state, and reaches protected root", async () => {
    const pending = deferred<typeof TEST_USER>();
    const register = vi.fn().mockReturnValue(pending.promise);
    const api = await renderRegistration({ register });
    completeRegistrationForm();
    const form = screen
      .getByRole("button", { name: "Create account" })
      .closest("form")!;

    fireEvent.submit(form);
    fireEvent.submit(form);

    expect(register).toHaveBeenCalledOnce();
    expect(register).toHaveBeenCalledWith({
      display_name: "  Sea Observer  ",
      email: "Observer@Example.com",
      password: PASSWORD,
    });
    expect(form).toHaveAttribute("aria-busy", "true");
    expect(
      screen.getByRole("button", { name: "Creating account..." }),
    ).toBeDisabled();
    expect(api.getCurrentUser).toHaveBeenCalledOnce();

    pending.resolve(TEST_USER);
    expect(
      await screen.findByRole("heading", { name: "Welcome to TrackSea" }),
    ).toBeInTheDocument();
    expect(JSON.stringify(TEST_USER)).not.toContain(PASSWORD);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("redirects an authenticated startup away from registration", async () => {
    renderAuthApp(
      fakeAuthApi({ getCurrentUser: vi.fn().mockResolvedValue(TEST_USER) }),
      "/register",
    );

    expect(
      await screen.findByRole("heading", { name: "Welcome to TrackSea" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  });

  it("fails closed on startup error without showing the form", async () => {
    renderAuthApp(
      fakeAuthApi({
        getCurrentUser: vi.fn().mockRejectedValue(new Error("private startup")),
      }),
      "/register",
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to determine the current session.",
    );
    expect(
      screen.queryByRole("button", { name: "Create account" }),
    ).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("private startup");
  });

  it("shows a generic registration conflict without method disclosure", async () => {
    const register = vi.fn().mockRejectedValue(
      new ApiError({
        status: 409,
        code: "account_conflict",
        message: "private account method detail",
      }),
    );
    await renderRegistration({ register });
    completeRegistrationForm();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "An account cannot be created with these details.",
    );
    expect(document.body).not.toHaveTextContent(
      "private account method detail",
    );
    expect(document.body).not.toHaveTextContent("uses Google");
  });

  it("maps validation issues to fields without exposing the password", async () => {
    const register = vi.fn().mockRejectedValue(
      new ApiError({
        status: 422,
        message: "Request validation failed.",
        validationIssues: [
          {
            location: ["body", "display_name"],
            message: "private",
            type: "value_error",
          },
          {
            location: ["body", "email"],
            message: "private",
            type: "value_error",
          },
          {
            location: ["body", "password"],
            message: PASSWORD,
            type: "value_error",
          },
        ],
      }),
    );
    await renderRegistration({ register });
    completeRegistrationForm();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    const password = screen.getByLabelText("Password");
    await waitFor(() =>
      expect(password).toHaveAttribute("aria-invalid", "true"),
    );
    expect(screen.getByLabelText("Display name")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(screen.getByLabelText("Email")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(password.getAttribute("aria-describedby")).toContain(
      "register-password-error",
    );
    expect(
      document.getElementById("register-password-error"),
    ).toHaveTextContent("Check the password and try again.");
    expect(
      document.getElementById("register-password-error"),
    ).not.toHaveTextContent(PASSWORD);
  });

  it.each([
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
    "keeps the form usable after a safe request failure",
    async (error, message) => {
      await renderRegistration({ register: vi.fn().mockRejectedValue(error) });
      completeRegistrationForm();
      fireEvent.click(screen.getByRole("button", { name: "Create account" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(
        screen.getByRole("button", { name: "Create account" }),
      ).toBeEnabled();
      expect(document.body).not.toHaveTextContent("private network detail");
      expect(document.body).not.toHaveTextContent("private CSRF");
    },
  );
});
