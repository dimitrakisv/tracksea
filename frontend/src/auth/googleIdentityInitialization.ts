type CredentialHandler = (credential: string) => void;

interface InitializationState {
  googleAccountsId: GoogleAccountsId;
  activeHandler: CredentialHandler | null;
}

const initializedClients = new Map<string, InitializationState>();

export function registerGoogleCredentialHandler(
  clientId: string,
  googleAccountsId: GoogleAccountsId,
  handler: CredentialHandler,
): () => void {
  let state = initializedClients.get(clientId);
  if (state === undefined) {
    state = { googleAccountsId, activeHandler: null };
    initializedClients.set(clientId, state);
    googleAccountsId.initialize({
      client_id: clientId,
      auto_select: false,
      callback: (response) => state?.activeHandler?.(response.credential),
    });
  } else if (state.googleAccountsId !== googleAccountsId) {
    throw new Error("Google Identity Services changed after initialization.");
  }

  // TrackSea currently renders one interactive GIS surface at a time.
  state.activeHandler = handler;
  return () => {
    if (state?.activeHandler === handler) state.activeHandler = null;
  };
}
