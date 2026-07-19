import { useId, useState, type FormEvent } from "react";

import { OneTimeKeyReveal } from "@/components/helios/one-time-key-reveal";
import { Eyebrow, StatusBadge } from "@/components/helios/primitives";
import { useProjectApiKeys } from "@/hooks/use-project-api-keys";
import {
  PROJECT_API_KEY_SCOPES,
  type ProjectApiKeyMetadata,
  type ProjectApiKeyScope,
} from "@/lib/api/user";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

const SCOPE_HELP: Record<ProjectApiKeyScope, string> = {
  "traces:ingest": "Authenticate OTLP ingestion (POST /v1/otlp/traces).",
  "traces:read": "Authenticate machine trace reads (GET /v2/traces).",
};

interface ProjectApiKeysPanelProps {
  projectId: string;
  projectName: string;
  projectSlug: string;
}

export function ProjectApiKeysPanel({
  projectId,
  projectName,
  projectSlug,
}: ProjectApiKeysPanelProps) {
  const state = useProjectApiKeys(projectId);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<ProjectApiKeyScope[]>(["traces:ingest", "traces:read"]);
  const [nameError, setNameError] = useState<string | null>(null);
  const [pendingRevoke, setPendingRevoke] = useState<ProjectApiKeyMetadata | null>(null);
  const nameId = useId();

  function toggleScope(scope: ProjectApiKeyScope) {
    setScopes((current) =>
      current.includes(scope) ? current.filter((item) => item !== scope) : [...current, scope],
    );
  }

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (state.creating) return;
    const trimmed = name.trim();
    if (!trimmed) {
      setNameError("Name is required");
      return;
    }
    if (scopes.length === 0) {
      setNameError("Select at least one scope");
      return;
    }
    setNameError(null);
    const ok = await state.createKey({ name: trimmed, scopes });
    if (ok) setName("");
  }

  return (
    <div className="space-y-6">
      <div>
        <Eyebrow>Selected project</Eyebrow>
        <p className="mt-1 text-[14px]">
          {projectName}{" "}
          <span className="font-mono text-[12px] text-muted-foreground">({projectSlug})</span>
        </p>
        <p className="mt-2 max-w-2xl text-[13px] text-muted-foreground leading-relaxed">
          Project API keys authenticate SDKs and OTLP clients. They are machine credentials: Helios
          stores only a hash, and the plaintext is shown once at creation.
        </p>
      </div>

      <section className="border border-rule">
        <div className="border-b border-rule px-4 py-3">
          <h2 className="font-serif text-lg">Create key</h2>
        </div>
        <form onSubmit={onCreate} className="space-y-4 px-4 py-4" noValidate>
          <div>
            <label htmlFor={nameId} className="label-eyebrow">
              Key name
            </label>
            <input
              id={nameId}
              type="text"
              value={name}
              disabled={state.creating}
              onChange={(event) => setName(event.target.value)}
              className="mt-1 w-full max-w-md border border-rule bg-paper px-2.5 py-2 text-[13px] outline-none focus:border-ink"
            />
          </div>
          <fieldset>
            <legend className="label-eyebrow">Scopes</legend>
            <ul className="mt-2 space-y-2">
              {PROJECT_API_KEY_SCOPES.map((scope) => (
                <li key={scope}>
                  <label className="flex items-start gap-2 text-[13px]">
                    <input
                      type="checkbox"
                      checked={scopes.includes(scope)}
                      disabled={state.creating}
                      onChange={() => toggleScope(scope)}
                      className="mt-1"
                    />
                    <span>
                      <span className="font-mono text-[12px]">{scope}</span>
                      <span className="mt-0.5 block text-[12px] text-muted-foreground">
                        {SCOPE_HELP[scope]}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
          {nameError || state.error ? (
            <p className="text-[12.5px] text-danger" role="alert">
              {nameError || state.error}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={state.creating}
            aria-busy={state.creating}
            className="border border-ink bg-ink px-3 py-2 text-[12.5px] text-paper disabled:opacity-50"
          >
            {state.creating ? "Creating…" : "Create API key"}
          </button>
        </form>
      </section>

      <section className="border border-rule">
        <div className="flex items-center justify-between border-b border-rule px-4 py-3">
          <h2 className="font-serif text-lg">Project API keys</h2>
          <button
            type="button"
            onClick={state.reload}
            className="label-eyebrow border border-rule px-2 py-1 hover:bg-paper-2"
          >
            Refresh
          </button>
        </div>
        {state.status === "loading" ? (
          <p className="px-4 py-4 text-[13px] text-muted-foreground" aria-busy="true">
            Loading keys…
          </p>
        ) : state.keys.length === 0 ? (
          <p className="px-4 py-4 text-[13px] text-muted-foreground">
            No keys yet. Create one to authenticate the SDK or OTLP exporter.
          </p>
        ) : (
          <ul className="divide-y divide-rule">
            {state.keys.map((key) => (
              <li
                key={key.id}
                className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[13.5px]">{key.name}</span>
                    <StatusBadge tone={key.status === "active" ? "success" : "neutral"}>
                      {key.status}
                    </StatusBadge>
                  </div>
                  <p className="mt-1 truncate font-mono text-[11.5px] text-muted-foreground">
                    {key.key_identifier}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                    {key.scopes.join(" · ")} · created {new Date(key.created_at).toISOString()}
                  </p>
                </div>
                {key.status === "active" ? (
                  <button
                    type="button"
                    onClick={() => setPendingRevoke(key)}
                    disabled={state.revokingId === key.id}
                    className="shrink-0 border border-rule px-2.5 py-1.5 text-[12px] hover:bg-paper-2 disabled:opacity-50"
                  >
                    Revoke
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <OneTimeKeyReveal created={state.reveal} onDismiss={state.dismissReveal} />

      <AlertDialog
        open={pendingRevoke !== null}
        onOpenChange={(open) => {
          if (!open) setPendingRevoke(null);
        }}
      >
        <AlertDialogContent className="rounded-none border-rule bg-paper sm:rounded-none">
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke this API key?</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingRevoke ? (
                <>
                  Clients using <strong>{pendingRevoke.name}</strong> (
                  <span className="font-mono">{pendingRevoke.key_identifier}</span>) will stop
                  authenticating immediately. This cannot be undone; create a new key if needed.
                </>
              ) : null}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-none">Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="rounded-none"
              onClick={() => {
                if (!pendingRevoke) return;
                const id = pendingRevoke.id;
                setPendingRevoke(null);
                void state.revokeKey(id);
              }}
            >
              Revoke key
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
