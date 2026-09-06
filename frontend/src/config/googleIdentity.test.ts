import { describe, expect, it } from "vitest";

import {
  GOOGLE_IDENTITY_UNAVAILABLE_MESSAGE,
  resolveGoogleIdentityConfiguration,
} from "./googleIdentity";

describe("Google identity configuration", () => {
  it.each([undefined, "", "   "])("treats %j as unconfigured", (value) => {
    expect(resolveGoogleIdentityConfiguration(value)).toEqual({
      status: "unconfigured",
      clientId: null,
      message: GOOGLE_IDENTITY_UNAVAILABLE_MESSAGE,
    });
  });

  it("exposes a trimmed configured public client ID", () => {
    expect(
      resolveGoogleIdentityConfiguration(
        "  tracksea.apps.googleusercontent.com  ",
      ),
    ).toEqual({
      status: "configured",
      clientId: "tracksea.apps.googleusercontent.com",
    });
  });
});
