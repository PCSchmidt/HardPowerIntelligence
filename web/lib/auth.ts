// Single source of truth for client-side password rules (D141).
//
// Signup and reset disagreed at first: reset enforced 8 characters while signup silently
// inherited Supabase's 6-character default. A user could therefore set a 6-char password at
// signup that the reset form would later refuse — the rule changing under them mid-relationship.
//
// NOTE: this is UX, not enforcement. Client-side checks are trivially bypassed; the real floor is
// Supabase's own minimum-password-length setting (Auth → Sign In / Providers → Email). Keep that
// set to MIN_PASSWORD too, or this is only a suggestion.
export const MIN_PASSWORD = 8;

/** Returns a human-readable problem with the password, or null when it's acceptable. */
export function passwordProblem(password: string, confirm?: string): string | null {
  if (password.length < MIN_PASSWORD) {
    return `Password must be at least ${MIN_PASSWORD} characters.`;
  }
  if (confirm !== undefined && password !== confirm) {
    return "Passwords don't match.";
  }
  return null;
}
