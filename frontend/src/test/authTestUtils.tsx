import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { App } from "../App";
import { ApiError } from "../api/client";
import type { AuthApi } from "../auth/api";
import { AuthProvider } from "../auth/AuthProvider";
import type { UserResponse } from "../auth/types";

export const TEST_USER: UserResponse = {
  id: "4140da29-bd94-4c62-bd5f-79b1c61468e7",
  email: "observer@example.com",
  email_verified: false,
  display_name: "Marine Observer",
  authentication_methods: ["password"],
};

export function fakeAuthApi(overrides: Partial<AuthApi> = {}): AuthApi {
  return {
    getCsrfToken: vi.fn().mockResolvedValue("unused"),
    register: vi.fn().mockResolvedValue(TEST_USER),
    login: vi.fn().mockResolvedValue(TEST_USER),
    logout: vi.fn().mockResolvedValue(undefined),
    getCurrentUser: vi.fn().mockRejectedValue(authenticationRequired()),
    updateProfile: vi.fn().mockResolvedValue(TEST_USER),
    googleSignIn: vi.fn().mockResolvedValue(TEST_USER),
    linkGoogle: vi.fn().mockResolvedValue(TEST_USER),
    ...overrides,
  };
}

export function authenticationRequired(): ApiError {
  return new ApiError({
    status: 401,
    code: "authentication_required",
    message: "Authentication is required.",
  });
}

export function deferred<T>(): {
  promise: Promise<T>;
  resolve(value: T): void;
  reject(reason: unknown): void;
} {
  let resolvePromise: ((value: T) => void) | undefined;
  let rejectPromise: ((reason: unknown) => void) | undefined;
  const promise = new Promise<T>((resolve, reject) => {
    resolvePromise = resolve;
    rejectPromise = reject;
  });
  return {
    promise,
    resolve(value) {
      resolvePromise?.(value);
    },
    reject(reason) {
      rejectPromise?.(reason);
    },
  };
}

export function renderAuthApp(
  api: AuthApi,
  path: string,
  observer?: ReactNode,
) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider api={api}>
        <App />
        {observer}
      </AuthProvider>
    </MemoryRouter>,
  );
}
