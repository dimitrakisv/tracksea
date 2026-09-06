import { createContext } from "react";

import type {
  GoogleCredentialRequest,
  LoginRequest,
  ProfileUpdateRequest,
  RegistrationRequest,
  UserResponse,
} from "./types";

export type AuthState =
  | { status: "loading"; user: null; error: null }
  | { status: "anonymous"; user: null; error: null }
  | { status: "authenticated"; user: UserResponse; error: null }
  | { status: "error"; user: null; error: { message: string } };

export interface AuthActions {
  register(request: RegistrationRequest): Promise<UserResponse>;
  login(request: LoginRequest): Promise<UserResponse>;
  logout(): Promise<void>;
  updateProfile(request: ProfileUpdateRequest): Promise<UserResponse>;
  googleSignIn(request: GoogleCredentialRequest): Promise<UserResponse>;
  linkGoogle(request: GoogleCredentialRequest): Promise<UserResponse>;
}

export type AuthContextValue = AuthState & AuthActions;

export const AuthContext = createContext<AuthContextValue | null>(null);
