import { describe, expect, it, vi } from "vitest";

import { registerGoogleCredentialHandler } from "./googleIdentityInitialization";

function fakeGoogleAccountsId() {
  return {
    initialize: vi.fn<GoogleAccountsId["initialize"]>(),
    renderButton: vi.fn<GoogleAccountsId["renderButton"]>(),
  };
}

describe("Google Identity Services initialization", () => {
  it("initializes once per client ID with automatic selection disabled", () => {
    const googleAccountsId = fakeGoogleAccountsId();
    const firstHandler = vi.fn();
    const secondHandler = vi.fn();

    registerGoogleCredentialHandler(
      "initialization-one.apps.googleusercontent.com",
      googleAccountsId,
      firstHandler,
    );
    registerGoogleCredentialHandler(
      "initialization-one.apps.googleusercontent.com",
      googleAccountsId,
      secondHandler,
    );

    expect(googleAccountsId.initialize).toHaveBeenCalledOnce();
    const configuration = googleAccountsId.initialize.mock.calls[0][0];
    expect(configuration.client_id).toBe(
      "initialization-one.apps.googleusercontent.com",
    );
    expect(configuration.auto_select).toBe(false);
    configuration.callback({ credential: "fresh-second-handler-credential" });
    expect(firstHandler).not.toHaveBeenCalled();
    expect(secondHandler).toHaveBeenCalledWith(
      "fresh-second-handler-credential",
    );
  });

  it("unregisters only the active handler and ignores late credentials", () => {
    const googleAccountsId = fakeGoogleAccountsId();
    const oldHandler = vi.fn();
    const activeHandler = vi.fn();
    const unregisterOld = registerGoogleCredentialHandler(
      "initialization-two.apps.googleusercontent.com",
      googleAccountsId,
      oldHandler,
    );
    const unregisterActive = registerGoogleCredentialHandler(
      "initialization-two.apps.googleusercontent.com",
      googleAccountsId,
      activeHandler,
    );
    const callback = googleAccountsId.initialize.mock.calls[0][0].callback;

    unregisterOld();
    callback({ credential: "active-credential" });
    expect(activeHandler).toHaveBeenCalledWith("active-credential");

    unregisterActive();
    callback({ credential: "late-credential" });
    expect(activeHandler).toHaveBeenCalledOnce();
  });

  it("initializes a different client ID independently", () => {
    const googleAccountsId = fakeGoogleAccountsId();

    registerGoogleCredentialHandler(
      "initialization-three-a.apps.googleusercontent.com",
      googleAccountsId,
      vi.fn(),
    );
    registerGoogleCredentialHandler(
      "initialization-three-b.apps.googleusercontent.com",
      googleAccountsId,
      vi.fn(),
    );

    expect(googleAccountsId.initialize).toHaveBeenCalledTimes(2);
  });
});
