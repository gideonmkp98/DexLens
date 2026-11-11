export function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

export function normalizeUsername(username: string): string {
  return username.trim().toLowerCase();
}

export function validateUsername(username?: string | null): {
  valid: boolean;
  error?: string;
} {
  if (!username) return { valid: true };
  const trimmed = username.trim();
  if (!trimmed) return { valid: true };
  const normalized = trimmed.toLowerCase();
  if (!/^[a-z0-9_-]{3,30}$/.test(normalized)) {
    return {
      valid: false,
      error:
        "Gebruikersnaam moet tussen 3 en 30 tekens lang zijn en mag alleen letters, cijfers, streepjes en underscores bevatten.",
    };
  }
  return { valid: true };
}

export function validateEmail(email: string): {
  valid: boolean;
  error?: string;
} {
  const normalized = normalizeEmail(email);
  if (!normalized || !normalized.includes("@")) {
    return { valid: false, error: "Vul een geldig e-mailadres in." };
  }
  return { valid: true };
}

export function validatePassword(
  password: string,
  minLength = 15,
  maxLength = 128
): { valid: boolean; error?: string } {
  if (!password || password.length < minLength) {
    return {
      valid: false,
      error: `Wachtwoord moet minimaal ${minLength} tekens bevatten.`,
    };
  }
  if (password.length > maxLength) {
    return {
      valid: false,
      error: `Wachtwoord mag maximaal ${maxLength} tekens bevatten.`,
    };
  }
  return { valid: true };
}

export function validateRegistration(fields: {
  username?: string | null;
  email: string;
  password: string;
  passwordConfirmation?: string;
  acceptedPolicies: boolean;
}): { valid: boolean; error?: string } {
  const emailVal = validateEmail(fields.email);
  if (!emailVal.valid) return emailVal;

  if (fields.username) {
    const userVal = validateUsername(fields.username);
    if (!userVal.valid) return userVal;
  }

  const passVal = validatePassword(fields.password, 15);
  if (!passVal.valid) return passVal;

  if (
    fields.passwordConfirmation &&
    fields.passwordConfirmation !== fields.password
  ) {
    return { valid: false, error: "Wachtwoorden komen niet overeen." };
  }

  if (!fields.acceptedPolicies) {
    return {
      valid: false,
      error:
        "Je moet akkoord gaan met de gebruiksvoorwaarden en het privacybeleid.",
    };
  }

  return { valid: true };
}
