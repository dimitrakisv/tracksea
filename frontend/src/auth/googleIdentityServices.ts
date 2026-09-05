export const GOOGLE_IDENTITY_SERVICES_URL =
  "https://accounts.google.com/gsi/client";

export class GoogleIdentityServicesLoadError extends Error {
  constructor() {
    super("Google sign-in could not be loaded.");
    this.name = "GoogleIdentityServicesLoadError";
  }
}

let loading: Promise<GoogleAccountsId> | null = null;

function loadedGoogleAccountsId(): GoogleAccountsId | null {
  return window.google?.accounts?.id ?? null;
}

export function loadGoogleIdentityServices(): Promise<GoogleAccountsId> {
  const loaded = loadedGoogleAccountsId();
  if (loaded) {
    return Promise.resolve(loaded);
  }
  if (loading) {
    return loading;
  }

  loading = new Promise<GoogleAccountsId>((resolve, reject) => {
    const selector = `script[src="${GOOGLE_IDENTITY_SERVICES_URL}"]`;
    const existingScript = document.querySelector<HTMLScriptElement>(selector);
    const script = existingScript ?? document.createElement("script");

    const fail = () => reject(new GoogleIdentityServicesLoadError());
    const complete = () => {
      const googleAccountsId = loadedGoogleAccountsId();
      if (!googleAccountsId) {
        fail();
        return;
      }
      resolve(googleAccountsId);
    };

    if (script.dataset.trackseaGisState === "loaded") {
      fail();
      return;
    }

    script.addEventListener("load", complete, { once: true });
    script.addEventListener("error", fail, { once: true });

    if (!existingScript) {
      script.src = GOOGLE_IDENTITY_SERVICES_URL;
      script.async = true;
      script.defer = true;
      script.dataset.trackseaGisState = "loading";
      script.addEventListener(
        "load",
        () => {
          script.dataset.trackseaGisState = "loaded";
        },
        { once: true },
      );
      document.head.append(script);
    }
  });

  return loading;
}
