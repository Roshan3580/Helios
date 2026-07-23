import { describe, expect, test } from "bun:test";

import type { UserMe } from "@/lib/api/user";
import { deriveWorkspaceState } from "./workspace-state";

function me(workosOrgId: string | null): UserMe {
  return {
    user_id: "u1",
    workos_user_id: "user_1",
    organization: {
      id: workosOrgId ? "local-org" : null,
      workos_org_id: workosOrgId,
      slug: workosOrgId ? "workspace-x" : null,
      name: workosOrgId ? "Workspace X" : null,
      linked: workosOrgId != null,
    },
    role: "member",
    permissions: [],
  };
}

describe("deriveWorkspaceState", () => {
  test("loading identity never gates prematurely", () => {
    expect(deriveWorkspaceState({ me: null, loading: true })).toBe("loading");
  });

  test("user with an active organization is ready", () => {
    expect(deriveWorkspaceState({ me: me("org_123"), loading: false })).toBe("ready");
  });

  test("user without any organization needs a workspace", () => {
    expect(deriveWorkspaceState({ me: me(null), loading: false })).toBe("needs_workspace");
  });

  test("unresolved identity (error/unauthenticated) does not gate", () => {
    expect(deriveWorkspaceState({ me: null, loading: false })).toBe("ready");
  });
});
