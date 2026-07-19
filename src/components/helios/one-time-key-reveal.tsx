import { useEffect, useRef, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { CreatedProjectApiKey } from "@/lib/api/user";

interface OneTimeKeyRevealProps {
  created: CreatedProjectApiKey | null;
  onDismiss: () => void;
}

export function OneTimeKeyReveal({ created, onDismiss }: OneTimeKeyRevealProps) {
  const open = created !== null;
  const keyRef = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) {
      setCopied(false);
      return;
    }
    const timer = window.setTimeout(() => keyRef.current?.focus(), 50);
    return () => window.clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  async function copyKey() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.plaintext_key);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onDismiss();
      }}
    >
      <DialogContent className="max-w-xl rounded-none border-rule bg-paper sm:rounded-none">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl">
            Copy this key now. Helios will not show it again.
          </DialogTitle>
          <DialogDescription className="text-[13px] text-muted-foreground">
            This plaintext project API key is shown once. After you dismiss this dialog, Helios
            cannot recover it — create another key if it is lost.
          </DialogDescription>
        </DialogHeader>

        {created ? (
          <div className="space-y-3">
            <div className="grid gap-1 text-[12.5px]">
              <div>
                <span className="label-eyebrow">Name</span>
                <div className="mt-0.5">{created.key.name}</div>
              </div>
              <div>
                <span className="label-eyebrow">Scopes</span>
                <div className="mt-0.5 font-mono text-[12px]">{created.key.scopes.join(", ")}</div>
              </div>
            </div>
            <pre
              ref={keyRef}
              tabIndex={0}
              className="overflow-x-auto border border-rule bg-paper-2 px-3 py-3 font-mono text-[12px] outline-none focus:border-ink"
              aria-label="New project API key"
            >
              {created.plaintext_key}
            </pre>
            <p className="text-[12px] text-muted-foreground" role="status">
              Store this key in your secret manager or environment variables. Do not commit it,
              paste it into browser storage, or share it in chat.
            </p>
          </div>
        ) : null}

        <DialogFooter className="gap-2 sm:justify-between">
          <button
            type="button"
            onClick={() => void copyKey()}
            className="border border-rule px-3 py-2 text-[12.5px] hover:bg-paper-2"
            aria-label="Copy project API key"
          >
            {copied ? "Copied" : "Copy key"}
          </button>
          <button
            type="button"
            onClick={onDismiss}
            className="border border-ink bg-ink px-3 py-2 text-[12.5px] text-paper"
          >
            I have copied the key
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
