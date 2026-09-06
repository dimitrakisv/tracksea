import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiError } from "../api/client";
import { authApi, type AuthApi } from "./api";
import {
  AuthContext,
  type AuthActions,
  type AuthContextValue,
  type AuthState,
} from "./context";
import type { UserResponse } from "./types";

interface AuthProviderProps {
  children: ReactNode;
  api?: AuthApi;
}

type StartupResult =
  | { status: "authenticated"; user: UserResponse }
  | { status: "anonymous" }
  | { status: "error" };

const startupRequests = new WeakMap<AuthApi, Promise<StartupResult>>();
const SESSION_LOAD_ERROR = "Unable to determine the current session.";

export function AuthProvider({ children, api = authApi }: AuthProviderProps) {
  const [state, setState] = useState<AuthState>({
    status: "loading",
    user: null,
    error: null,
  });

  useEffect(() => {
    let active = true;
    getStartupResult(api).then((result) => {
      if (!active) return;
      if (result.status === "authenticated") {
        setState({
          status: "authenticated",
          user: result.user,
          error: null,
        });
      } else if (result.status === "anonymous") {
        setState({ status: "anonymous", user: null, error: null });
      } else {
        setState({
          status: "error",
          user: null,
          error: { message: SESSION_LOAD_ERROR },
        });
      }
    });
    return () => {
      active = false;
    };
  }, [api]);

  const authenticate = useCallback(
    async (operation: () => Promise<UserResponse>): Promise<UserResponse> => {
      const user = await operation();
      setState({ status: "authenticated", user, error: null });
      return user;
    },
    [],
  );

  const updateAuthenticatedUser = useCallback(
    async (operation: () => Promise<UserResponse>): Promise<UserResponse> => {
      try {
        const user = await operation();
        setState({ status: "authenticated", user, error: null });
        return user;
      } catch (error) {
        if (isAuthenticationRequired(error)) {
          setState({ status: "anonymous", user: null, error: null });
        }
        throw error;
      }
    },
    [],
  );

  const actions = useMemo<AuthActions>(
    () => ({
      register: (request) => authenticate(() => api.register(request)),
      login: (request) => authenticate(() => api.login(request)),
      googleSignIn: (request) => authenticate(() => api.googleSignIn(request)),
      updateProfile: (request) =>
        updateAuthenticatedUser(() => api.updateProfile(request)),
      linkGoogle: (request) =>
        updateAuthenticatedUser(() => api.linkGoogle(request)),
      logout: async () => {
        await api.logout();
        setState({ status: "anonymous", user: null, error: null });
      },
    }),
    [api, authenticate, updateAuthenticatedUser],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, ...actions }),
    [actions, state],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function getStartupResult(api: AuthApi): Promise<StartupResult> {
  const existing = startupRequests.get(api);
  if (existing !== undefined) return existing;

  const request = api
    .getCurrentUser()
    .then<StartupResult>((user) => ({ status: "authenticated", user }))
    .catch<StartupResult>((error: unknown) =>
      isAuthenticationRequired(error)
        ? { status: "anonymous" }
        : { status: "error" },
    )
    .finally(() => {
      if (startupRequests.get(api) === request) startupRequests.delete(api);
    });
  startupRequests.set(api, request);
  return request;
}

function isAuthenticationRequired(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.status === 401 &&
    error.code === "authentication_required"
  );
}
