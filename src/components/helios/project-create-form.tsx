import { useEffect, useId, useState, type FormEvent } from "react";
import { useHeliosAccessToken as useAccessToken } from "@/lib/auth/helios-auth";

import { useProjectSelection } from "@/contexts/project-selection";
import { createUserProject, UserApiError } from "@/lib/api/user";
import { redirectToSignIn } from "@/lib/auth/redirect-to-sign-in";
import {
  slugifyProjectName,
  validateProjectName,
  validateProjectSlug,
} from "@/lib/onboarding/slug";

interface ProjectCreateFormProps {
  onCreated?: (projectId: string) => void;
}

export function ProjectCreateForm({ onCreated }: ProjectCreateFormProps) {
  const { getAccessToken } = useAccessToken();
  const { refreshProjects, selectProject } = useProjectSelection();
  const nameId = useId();
  const slugId = useId();
  const errorId = useId();

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [slugError, setSlugError] = useState<string | null>(null);

  useEffect(() => {
    if (!slugTouched) {
      setSlug(slugifyProjectName(name));
    }
  }, [name, slugTouched]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    const nextNameError = validateProjectName(name);
    const nextSlugError = validateProjectSlug(slug);
    setNameError(nextNameError);
    setSlugError(nextSlugError);
    setFormError(null);
    if (nextNameError || nextSlugError) return;

    setSubmitting(true);
    try {
      const token = await getAccessToken();
      if (!token) {
        redirectToSignIn();
        return;
      }
      const project = await createUserProject(token, {
        name: name.trim(),
        slug: slug.trim().toLowerCase(),
      });
      selectProject(project.id);
      refreshProjects();
      onCreated?.(project.id);
      setName("");
      setSlug("");
      setSlugTouched(false);
    } catch (err) {
      if (err instanceof UserApiError && err.status === 401) {
        redirectToSignIn();
        return;
      }
      if (err instanceof UserApiError && err.status === 409) {
        setFormError("A project with this slug already exists.");
        return;
      }
      if (err instanceof UserApiError && err.status === 422) {
        setFormError(err.message);
        return;
      }
      setFormError(err instanceof Error ? err.message : "Could not create project");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <div>
        <label htmlFor={nameId} className="label-eyebrow">
          Project name
        </label>
        <input
          id={nameId}
          name="name"
          type="text"
          autoComplete="off"
          value={name}
          disabled={submitting}
          aria-invalid={Boolean(nameError)}
          aria-describedby={nameError ? `${nameId}-error` : undefined}
          onChange={(event) => setName(event.target.value)}
          className="mt-1 w-full border border-rule bg-paper px-2.5 py-2 text-[13px] outline-none focus:border-ink disabled:opacity-60"
        />
        {nameError ? (
          <p id={`${nameId}-error`} className="mt-1 text-[12px] text-danger" role="alert">
            {nameError}
          </p>
        ) : null}
      </div>

      <div>
        <label htmlFor={slugId} className="label-eyebrow">
          Project slug
        </label>
        <input
          id={slugId}
          name="slug"
          type="text"
          autoComplete="off"
          value={slug}
          disabled={submitting}
          aria-invalid={Boolean(slugError)}
          aria-describedby={slugError ? `${slugId}-error` : undefined}
          onChange={(event) => {
            setSlugTouched(true);
            setSlug(event.target.value.toLowerCase());
          }}
          className="mt-1 w-full border border-rule bg-paper px-2.5 py-2 font-mono text-[12.5px] outline-none focus:border-ink disabled:opacity-60"
        />
        {slugError ? (
          <p id={`${slugId}-error`} className="mt-1 text-[12px] text-danger" role="alert">
            {slugError}
          </p>
        ) : (
          <p className="mt-1 text-[11.5px] text-muted-foreground">
            Lowercase letters, numbers, and hyphens. Unique across Helios.
          </p>
        )}
      </div>

      {formError ? (
        <p id={errorId} className="text-[12.5px] text-danger" role="alert">
          {formError}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={submitting}
        aria-busy={submitting}
        className="border border-ink bg-ink px-3 py-2 text-[12.5px] text-paper disabled:opacity-50"
      >
        {submitting ? "Creating…" : "Create project"}
      </button>
    </form>
  );
}
