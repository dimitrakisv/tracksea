import { afterEach, describe, expect, it, vi } from "vitest";

const SCRIPT_URL = "https://accounts.google.com/gsi/client";

async function loadModule() {
  return import("./googleIdentityServices");
}

afterEach(() => {
  document.head.replaceChildren();
  delete window.google;
  vi.restoreAllMocks();
  vi.resetModules();
});

describe("Google Identity Services loader", () => {
  it("loads the official script once and shares concurrent work", async () => {
    const { GOOGLE_IDENTITY_SERVICES_URL, loadGoogleIdentityServices } =
      await loadModule();

    const first = loadGoogleIdentityServices();
    const second = loadGoogleIdentityServices();
    const scripts = document.querySelectorAll<HTMLScriptElement>(
      `script[src="${SCRIPT_URL}"]`,
    );

    expect(GOOGLE_IDENTITY_SERVICES_URL).toBe(SCRIPT_URL);
    expect(first).toBe(second);
    expect(scripts).toHaveLength(1);
    expect(scripts[0].async).toBe(true);
    expect(scripts[0].defer).toBe(true);

    const initialize = vi.fn();
    const renderButton = vi.fn();
    window.google = { accounts: { id: { initialize, renderButton } } };
    scripts[0].dispatchEvent(new Event("load"));

    await expect(first).resolves.toBe(window.google.accounts.id);
    expect(initialize).not.toHaveBeenCalled();
    expect(renderButton).not.toHaveBeenCalled();
    expect(document.querySelector("button")).toBeNull();
  });

  it("reuses an existing loaded GIS global without adding a script", async () => {
    const initialize = vi.fn();
    const renderButton = vi.fn();
    window.google = { accounts: { id: { initialize, renderButton } } };
    const { loadGoogleIdentityServices } = await loadModule();

    await expect(loadGoogleIdentityServices()).resolves.toBe(
      window.google.accounts.id,
    );

    expect(document.scripts).toHaveLength(0);
    expect(initialize).not.toHaveBeenCalled();
    expect(renderButton).not.toHaveBeenCalled();
  });

  it("reuses an existing in-flight official script", async () => {
    const existing = document.createElement("script");
    existing.src = SCRIPT_URL;
    document.head.append(existing);
    const { loadGoogleIdentityServices } = await loadModule();

    const result = loadGoogleIdentityServices();
    expect(
      document.querySelectorAll(`script[src="${SCRIPT_URL}"]`),
    ).toHaveLength(1);

    window.google = {
      accounts: { id: { initialize: vi.fn(), renderButton: vi.fn() } },
    };
    existing.dispatchEvent(new Event("load"));
    await expect(result).resolves.toBe(window.google.accounts.id);
  });

  it("returns one controlled failure without retrying or duplicating scripts", async () => {
    const { GoogleIdentityServicesLoadError, loadGoogleIdentityServices } =
      await loadModule();
    const first = loadGoogleIdentityServices();
    const script = document.querySelector<HTMLScriptElement>(
      `script[src="${SCRIPT_URL}"]`,
    );
    expect(script).not.toBeNull();
    script?.dispatchEvent(new Event("error"));

    await expect(first).rejects.toBeInstanceOf(GoogleIdentityServicesLoadError);
    const second = loadGoogleIdentityServices();
    expect(second).toBe(first);
    await expect(second).rejects.toThrow("Google sign-in could not be loaded.");
    expect(
      document.querySelectorAll(`script[src="${SCRIPT_URL}"]`),
    ).toHaveLength(1);
  });

  it("does not persist browser state while loading", async () => {
    const localStorageWrite = vi.spyOn(Storage.prototype, "setItem");
    const { loadGoogleIdentityServices } = await loadModule();
    const result = loadGoogleIdentityServices();
    const script = document.querySelector<HTMLScriptElement>(
      `script[src="${SCRIPT_URL}"]`,
    );
    window.google = {
      accounts: { id: { initialize: vi.fn(), renderButton: vi.fn() } },
    };
    script?.dispatchEvent(new Event("load"));
    await result;

    expect(localStorageWrite).not.toHaveBeenCalled();
  });
});
