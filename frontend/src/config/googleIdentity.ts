export const GOOGLE_IDENTITY_UNAVAILABLE_MESSAGE =
  "Google sign-in is not configured.";

export type GoogleIdentityConfiguration =
  | { status: "configured"; clientId: string }
  | {
      status: "unconfigured";
      clientId: null;
      message: typeof GOOGLE_IDENTITY_UNAVAILABLE_MESSAGE;
    };

export function resolveGoogleIdentityConfiguration(
  value: string | undefined,
): GoogleIdentityConfiguration {
  const clientId = value?.trim();
  if (!clientId) {
    return {
      status: "unconfigured",
      clientId: null,
      message: GOOGLE_IDENTITY_UNAVAILABLE_MESSAGE,
    };
  }
  return { status: "configured", clientId };
}

export const googleIdentityConfiguration = resolveGoogleIdentityConfiguration(
  import.meta.env.VITE_GOOGLE_CLIENT_ID,
);
