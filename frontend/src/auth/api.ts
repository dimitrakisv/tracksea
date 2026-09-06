import { ApiError, createApiClient, type ApiClient } from "../api/client";
import type {
  CsrfResponse,
  GoogleCredentialRequest,
  LoginRequest,
  ProfileUpdateRequest,
  RegistrationRequest,
  RequestOptions,
  UserResponse,
} from "./types";

export interface AuthApi {
  getCsrfToken(options?: RequestOptions): Promise<string>;
  register(
    request: RegistrationRequest,
    options?: RequestOptions,
  ): Promise<UserResponse>;
  login(request: LoginRequest, options?: RequestOptions): Promise<UserResponse>;
  logout(options?: RequestOptions): Promise<void>;
  getCurrentUser(options?: RequestOptions): Promise<UserResponse>;
  updateProfile(
    request: ProfileUpdateRequest,
    options?: RequestOptions,
  ): Promise<UserResponse>;
  googleSignIn(
    request: GoogleCredentialRequest,
    options?: RequestOptions,
  ): Promise<UserResponse>;
  linkGoogle(
    request: GoogleCredentialRequest,
    options?: RequestOptions,
  ): Promise<UserResponse>;
}

export function createAuthApi(client: ApiClient = createApiClient()): AuthApi {
  let csrfToken: string | undefined;
  let csrfRequest: Promise<string> | undefined;

  const invalidateCsrf = (): void => {
    csrfToken = undefined;
  };

  const getCsrfToken = (options: RequestOptions = {}): Promise<string> => {
    if (csrfToken !== undefined) return Promise.resolve(csrfToken);
    if (csrfRequest !== undefined) return csrfRequest;

    csrfRequest = client
      .request<CsrfResponse>("/api/v1/auth/csrf", { signal: options.signal })
      .then((response) => {
        if (
          typeof response.csrf_token !== "string" ||
          response.csrf_token.length === 0
        ) {
          throw new ApiError({
            status: 200,
            message: "Unexpected server response.",
          });
        }
        csrfToken = response.csrf_token;
        return csrfToken;
      })
      .finally(() => {
        csrfRequest = undefined;
      });
    return csrfRequest;
  };

  const unsafeRequest = async <T>(
    path: string,
    method: "POST" | "PATCH",
    body: unknown,
    options: RequestOptions,
  ): Promise<T> => {
    const token = await getCsrfToken(options);
    try {
      return await client.request<T>(path, {
        method,
        body,
        headers: { "X-CSRF-Token": token },
        signal: options.signal,
      });
    } catch (error) {
      if (error instanceof ApiError && error.code === "csrf_failed") {
        invalidateCsrf();
      }
      throw error;
    }
  };

  const transition = async <T>(operation: () => Promise<T>): Promise<T> => {
    const result = await operation();
    invalidateCsrf();
    return result;
  };

  return {
    getCsrfToken,
    register: (request, options = {}) =>
      transition(() =>
        unsafeRequest<UserResponse>(
          "/api/v1/auth/register",
          "POST",
          request,
          options,
        ),
      ),
    login: (request, options = {}) =>
      transition(() =>
        unsafeRequest<UserResponse>(
          "/api/v1/auth/login",
          "POST",
          request,
          options,
        ),
      ),
    logout: (options = {}) =>
      transition(() =>
        unsafeRequest<void>("/api/v1/auth/logout", "POST", undefined, options),
      ),
    getCurrentUser: (options = {}) =>
      client.request<UserResponse>("/api/v1/auth/me", {
        signal: options.signal,
      }),
    updateProfile: (request, options = {}) =>
      unsafeRequest<UserResponse>(
        "/api/v1/users/me",
        "PATCH",
        request,
        options,
      ),
    googleSignIn: (request, options = {}) =>
      transition(() =>
        unsafeRequest<UserResponse>(
          "/api/v1/auth/google",
          "POST",
          request,
          options,
        ),
      ),
    linkGoogle: (request, options = {}) =>
      unsafeRequest<UserResponse>(
        "/api/v1/auth/google/link",
        "POST",
        request,
        options,
      ),
  };
}

export const authApi = createAuthApi();
