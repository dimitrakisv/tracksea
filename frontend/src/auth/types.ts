export type AuthenticationMethod = "password" | "google";

export interface UserResponse {
  id: string;
  email: string;
  email_verified: boolean;
  display_name: string;
  authentication_methods: AuthenticationMethod[];
}

export interface RegistrationRequest {
  email: string;
  password: string;
  display_name: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface ProfileUpdateRequest {
  display_name: string;
}

export interface GoogleCredentialRequest {
  credential: string;
}

export interface CsrfResponse {
  csrf_token: string;
}

export type AuthErrorCode =
  | "authentication_required"
  | "invalid_credentials"
  | "account_conflict"
  | "account_link_required"
  | "csrf_failed"
  | "rate_limited";

export interface ValidationIssue {
  location: Array<string | number>;
  message: string;
  type: string;
}

export interface RequestOptions {
  signal?: AbortSignal;
}
