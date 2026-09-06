import { useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import type { AuthContextValue } from "../auth/context";
import { appCopy } from "./copy";
import "./AuthenticatedShell.css";

export interface AuthenticatedOutletContext {
  auth: Extract<AuthContextValue, { status: "authenticated" }>;
}

export function AuthenticatedShell() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const logoutPending = useRef(false);

  if (auth.status !== "authenticated") return null;

  async function handleLogout() {
    if (logoutPending.current) return;
    logoutPending.current = true;
    setLoggingOut(true);
    setLogoutError(null);
    try {
      await auth.logout();
      navigate("/sign-in", { replace: true });
    } catch {
      logoutPending.current = false;
      setLoggingOut(false);
      setLogoutError("Unable to sign out. Please try again.");
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__inner">
          <div className="app-brand">
            <NavLink to="/" end className="app-brand__name">
              {appCopy.name}
            </NavLink>
            <p>{appCopy.tagline}</p>
          </div>

          <nav className="app-navigation" aria-label="Primary">
            <NavLink to="/" end>
              Home
            </NavLink>
            <NavLink to="/profile">Profile</NavLink>
          </nav>

          <div className="app-user">
            <div className="app-user__identity">
              <strong>{auth.user.display_name}</strong>
              <span>{auth.user.email}</span>
            </div>
            <button
              type="button"
              onClick={() => void handleLogout()}
              disabled={loggingOut}
              aria-busy={loggingOut}
            >
              {loggingOut ? "Signing out..." : "Sign out"}
            </button>
          </div>
        </div>
        {logoutError !== null && (
          <p className="app-header__error" role="alert">
            {logoutError}
          </p>
        )}
      </header>

      <main className="app-main">
        <Outlet context={{ auth } satisfies AuthenticatedOutletContext} />
      </main>
    </div>
  );
}
