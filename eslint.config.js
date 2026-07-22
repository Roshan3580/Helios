import js from "@eslint/js";
import eslintPluginPrettier from "eslint-plugin-prettier/recommended";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      // Build output
      "dist",
      ".output",
      ".vinxi",
      ".vercel/**",
      ".tanstack/**",
      ".nitro/**",
      ".vite/**",
      // Playwright (fixtures use Playwright's `use`, not React hooks)
      "e2e/**",
      "playwright.config.ts",
      "playwright-report/**",
      "test-results/**",
      // Python virtual environments and bytecode caches
      "**/.venv/**",
      ".venv-demo/**",
      "**/__pycache__/**",
      "**/*.egg-info/**",
      // TypeScript SDK + Node examples: standalone npm package with its own
      // typecheck/test/package gates (frontend browser rules do not apply)
      "sdk/typescript/**",
      "examples/typescript-basic/**",
      "examples/typescript-openai/**",
    ],
  },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "server-only",
              message:
                "TanStack Start does not use the Next.js `server-only` package. Rename the module to `*.server.ts` or mark it with `@tanstack/react-start/server-only`.",
            },
          ],
        },
      ],
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-unused-vars": "off",
    },
  },
  eslintPluginPrettier,
);
