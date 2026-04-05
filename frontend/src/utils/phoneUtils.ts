// frontend/src/utils/phoneUtils.ts

import { parsePhoneNumber, isValidPhoneNumber, type CountryCode } from 'libphonenumber-js';

export interface PhoneValidationResult {
  isValid: boolean;
  e164: string | null;
  displayFormat: string | null;
  error: string | null;
  detectedCountry: CountryCode | null;
}

/**
 * Validates and normalizes a phone number to E.164 format for Twilio.
 *
 * Rules (in order of priority):
 * 1. If input is exactly 10 digits → assume India (+91)
 * 2. If input starts with 91 and has 12 digits → strip leading 91, apply +91
 * 3. If input starts with + → parse as international
 * 4. If input starts with 00 → replace 00 with + and parse
 * 5. All other cases → invalid
 *
 * @param rawInput - Raw string typed by user (may include spaces, dashes, brackets)
 * @param defaultCountry - ISO country code for ambiguous numbers (default: 'IN')
 */
export function validateAndFormatPhone(
  rawInput: string,
  defaultCountry: CountryCode = 'IN'
): PhoneValidationResult {
  const invalid = (error: string): PhoneValidationResult => ({
    isValid: false, e164: null, displayFormat: null, error, detectedCountry: null
  });

  if (!rawInput || rawInput.trim() === '') {
    return invalid('Phone number is required.');
  }

  // Strip all non-digit, non-plus characters for analysis
  const digitsOnly = rawInput.replace(/\D/g, '');
  const stripped = rawInput.trim();

  // Rule 1: Exactly 10 digits → Indian mobile number
  if (digitsOnly.length === 10) {
    const candidate = `+91${digitsOnly}`;
    if (isValidPhoneNumber(candidate, defaultCountry)) {
      const parsed = parsePhoneNumber(candidate, defaultCountry);
      return {
        isValid: true,
        e164: parsed.format('E.164'),
        displayFormat: parsed.formatInternational(),
        error: null,
        detectedCountry: defaultCountry
      };
    }
    return invalid(`"${rawInput}" is not a valid Indian mobile number. Check the digits.`);
  }

  // Rule 2: 12 digits starting with 91 → likely typed with country code without +
  if (digitsOnly.length === 12 && digitsOnly.startsWith('91')) {
    const candidate = `+${digitsOnly}`;
    if (isValidPhoneNumber(candidate, defaultCountry)) {
      const parsed = parsePhoneNumber(candidate, defaultCountry);
      return {
        isValid: true,
        e164: parsed.format('E.164'),
        displayFormat: parsed.formatInternational(),
        error: null,
        detectedCountry: defaultCountry
      };
    }
  }

  // Rule 3: Starts with 00 → international prefix
  const normalizedInput = stripped.startsWith('00')
    ? `+${stripped.slice(2)}`
    : stripped;

  // Rule 4: Try parsing as international (with or without +)
  try {
    const candidate = normalizedInput.startsWith('+')
      ? normalizedInput
      : `+${digitsOnly}`;

    if (isValidPhoneNumber(candidate)) {
      const parsed = parsePhoneNumber(candidate);
      const country = parsed.country as CountryCode;
      return {
        isValid: true,
        e164: parsed.format('E.164'),
        displayFormat: parsed.formatInternational(),
        error: null,
        detectedCountry: country || null
      };
    }
  } catch (e) {
    // parsePhoneNumber throws on genuinely invalid input
  }

  return invalid(
    `Could not parse "${rawInput}" as a valid phone number. ` +
    `For India, enter 10 digits (e.g., 9307201890) or use international format (+91XXXXXXXXXX).`
  );
}

/**
 * Formats a raw input progressively as the user types.
 * Used for input field display — does not validate.
 */
export function formatPhoneAsTyped(input: string): string {
  const digits = input.replace(/\D/g, '');
  if (digits.length <= 10) {
    // Format Indian mobile: XXXXX XXXXX
    return digits.replace(/(\d{5})(\d{1,5})/, '$1 $2');
  }
  return input; // Don't reformat international numbers
}
