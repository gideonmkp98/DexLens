import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  normalizeEmail,
  normalizeUsername,
  validateUsername,
  validateEmail,
  validatePassword,
  validateRegistration,
} from "./authValidation.ts";

describe("Phase 9 Auth Validation Suite", () => {
  describe("Email normalization & validation", () => {
    test("normalizes email to lower case and trims whitespace", () => {
      assert.equal(
        normalizeEmail("  Ash.Ketchum@Kanto.Org  "),
        "ash.ketchum@kanto.org"
      );
    });

    test("rejects invalid email formats", () => {
      const res = validateEmail("invalid-email");
      assert.equal(res.valid, false);
      assert.equal(res.error, "Vul een geldig e-mailadres in.");
    });

    test("accepts valid email format", () => {
      const res = validateEmail("trainer@pallet.town");
      assert.equal(res.valid, true);
      assert.equal(res.error, undefined);
    });
  });

  describe("Username normalization & validation", () => {
    test("normalizes username to lower case and trims", () => {
      assert.equal(normalizeUsername("  Red_Master99  "), "red_master99");
    });

    test("allows empty or omitted username (optional on register)", () => {
      assert.equal(validateUsername(undefined).valid, true);
      assert.equal(validateUsername("").valid, true);
      assert.equal(validateUsername("   ").valid, true);
    });

    test("rejects usernames too short or too long", () => {
      const tooShort = validateUsername("ab");
      assert.equal(tooShort.valid, false);
      assert.match(tooShort.error || "", /tussen 3 en 30 tekens/);

      const tooLong = validateUsername("a".repeat(31));
      assert.equal(tooLong.valid, false);
    });

    test("rejects special characters other than _ and -", () => {
      const special = validateUsername("ash.ketchum!");
      assert.equal(special.valid, false);

      const validOne = validateUsername("ash_ketchum-99");
      assert.equal(validOne.valid, true);
    });
  });

  describe("Modern Password Policy (NIST SP 800-63B)", () => {
    test("requires at least 15 characters for password-only authentication", () => {
      const shortPass = validatePassword("ShortPass1234");
      assert.equal(shortPass.valid, false);
      assert.equal(
        shortPass.error,
        "Wachtwoord moet minimaal 15 tekens bevatten."
      );
    });

    test("accepts passwords >= 15 characters with spaces, unicode, and passphrases", () => {
      const pass = "correct horse battery staple 2026!";
      assert.equal(validatePassword(pass).valid, true);

      const unicodePass = "Pikachu⚡Metagross🛡️Charizard🔥";
      assert.equal(validatePassword(unicodePass).valid, true);
    });

    test("rejects passwords exceeding 128 characters", () => {
      const extreme = "a".repeat(129);
      const res = validatePassword(extreme);
      assert.equal(res.valid, false);
      assert.match(res.error || "", /maximaal 128 tekens/);
    });
  });

  describe("Registration form completeness", () => {
    const validData = {
      username: "kanto_champion",
      email: "red@indigo.plateau",
      password: "DexLensUnpwnedPassword2026!",
      passwordConfirmation: "DexLensUnpwnedPassword2026!",
      acceptedPolicies: true,
    };

    test("validates complete valid registration", () => {
      const res = validateRegistration(validData);
      assert.equal(res.valid, true);
    });

    test("enforces password confirmation match", () => {
      const res = validateRegistration({
        ...validData,
        passwordConfirmation: "DifferentPassword2026!",
      });
      assert.equal(res.valid, false);
      assert.equal(res.error, "Wachtwoorden komen niet overeen.");
    });

    test("enforces acceptance of site policies", () => {
      const res = validateRegistration({
        ...validData,
        acceptedPolicies: false,
      });
      assert.equal(res.valid, false);
      assert.equal(
        res.error,
        "Je moet akkoord gaan met de gebruiksvoorwaarden en het privacybeleid."
      );
    });
  });
});
