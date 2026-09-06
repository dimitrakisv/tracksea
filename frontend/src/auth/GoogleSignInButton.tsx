import { useEffect, useEffectEvent, useRef, useState } from "react";

import { ApiError } from "../api/client";
import { googleIdentityConfiguration } from "../config/googleIdentity";
import { registerGoogleCredentialHandler } from "./googleIdentityInitialization";
import { loadGoogleIdentityServices } from "./googleIdentityServices";
import type { UserResponse } from "./types";
import { useAuth } from "./useAuth";

export type GoogleSignInMode = "authenticate" | "link";
export type GoogleButtonText = "signin_with" | "signup_with" | "continue_with";

interface GoogleSignInButtonProps {
  mode: GoogleSignInMode;
  buttonText: GoogleButtonText;
  onSuccess(user: UserResponse): void;
  onAccountLinkRequired?(): void;
}

type LoadState = "loading" | "ready" | "error";

export function GoogleSignInButton({
  mode,
  buttonText,
  onSuccess,
  onAccountLinkRequired,
}: GoogleSignInButtonProps) {
  const auth = useAuth();
  const buttonHostRef = useRef<HTMLDivElement>(null);
  const busyRef = useRef(false);
  const componentActiveRef = useRef(false);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const submitCredential = useEffectEvent(
    async (candidate: string): Promise<void> => {
      if (busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      setErrorMessage(null);
      let credential = candidate;
      try {
        const user =
          mode === "authenticate"
            ? await auth.googleSignIn({ credential })
            : await auth.linkGoogle({ credential });
        if (componentActiveRef.current) onSuccess(user);
      } catch (error) {
        if (
          mode === "authenticate" &&
          error instanceof ApiError &&
          error.status === 409 &&
          error.code === "account_link_required"
        ) {
          if (componentActiveRef.current) onAccountLinkRequired?.();
        } else if (componentActiveRef.current) {
          setErrorMessage(googleErrorMessage(error, mode));
        }
      } finally {
        credential = "";
        busyRef.current = false;
        if (componentActiveRef.current) setBusy(false);
      }
    },
  );

  useEffect(() => {
    componentActiveRef.current = true;
    return () => {
      componentActiveRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (googleIdentityConfiguration.status === "unconfigured") return;
    const clientId = googleIdentityConfiguration.clientId;

    let active = true;
    let unregisterHandler: (() => void) | undefined;
    const buttonHost = buttonHostRef.current;

    void loadGoogleIdentityServices()
      .then((googleAccountsId) => {
        if (!active || buttonHost === null) return;
        unregisterHandler = registerGoogleCredentialHandler(
          clientId,
          googleAccountsId,
          (credential) => void submitCredential(credential),
        );
        buttonHost.replaceChildren();
        googleAccountsId.renderButton(buttonHost, {
          type: "standard",
          theme: "outline",
          size: "large",
          text: buttonText,
          shape: "rectangular",
          logo_alignment: "left",
        });
        setLoadState("ready");
      })
      .catch(() => {
        if (!active) return;
        setLoadState("error");
      });

    return () => {
      active = false;
      unregisterHandler?.();
      buttonHost?.replaceChildren();
    };
  }, [buttonText, mode]);

  if (googleIdentityConfiguration.status === "unconfigured") {
    return (
      <div className="google-auth" role="status">
        {googleIdentityConfiguration.message}
      </div>
    );
  }

  return (
    <div
      className="google-auth"
      aria-busy={busy}
      aria-label="Google authentication"
    >
      <div className="google-auth__button" ref={buttonHostRef} />
      {loadState === "loading" && (
        <p role="status">Loading Google sign-in...</p>
      )}
      {loadState === "error" && (
        <p role="alert">
          Google sign-in could not be loaded. You can still use email and
          password.
        </p>
      )}
      {busy && <p role="status">Completing Google sign-in...</p>}
      {errorMessage !== null && <p role="alert">{errorMessage}</p>}
    </div>
  );
}

function googleErrorMessage(error: unknown, mode: GoogleSignInMode): string {
  if (error instanceof ApiError) {
    if (error.status === 403 && error.code === "csrf_failed") {
      return "The request could not be verified. Please try again.";
    }
    if (
      mode === "link" &&
      error.status === 409 &&
      error.code === "account_conflict"
    ) {
      return "The Google account could not be linked.";
    }
    if (error.status === 401 && error.code === "invalid_credentials") {
      return mode === "link"
        ? "Google account could not be verified."
        : "Google sign-in could not be completed.";
    }
  }
  return mode === "link"
    ? "Unable to link the Google account. Please try again."
    : "Unable to complete Google sign-in. Please try again.";
}
