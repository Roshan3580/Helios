/** Client-side project slug helpers. Server validation remains authoritative. */

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function slugifyProjectName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-")
    .slice(0, 128);
}

export function validateProjectSlug(slug: string): string | null {
  const value = slug.trim().toLowerCase();
  if (!value) return "Slug is required";
  if (value.length > 128) return "Slug must be at most 128 characters";
  if (value.startsWith("-") || value.endsWith("-")) {
    return "Slug must not start or end with a hyphen";
  }
  if (value.includes("--")) return "Slug must not contain consecutive hyphens";
  if (!SLUG_RE.test(value)) {
    return "Slug may contain only lowercase letters, numbers, and hyphens";
  }
  return null;
}

export function validateProjectName(name: string): string | null {
  const value = name.trim();
  if (!value) return "Name is required";
  if (value.length > 255) return "Name must be at most 255 characters";
  return null;
}
