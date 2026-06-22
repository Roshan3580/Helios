import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/helios/app-shell";

export const Route = createFileRoute("/app")({
  head: () => ({ meta: [{ title: "Helios — Observatory" }] }),
  component: AppShell,
});
