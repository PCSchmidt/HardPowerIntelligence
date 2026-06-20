import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Vitest for the web app. We deliberately do NOT use @vitejs/plugin-react — its Babel
// chain conflicts with the modified Next's @babel/core. Vitest 4's built-in oxc transform
// handles the automatic JSX runtime (React 19) for tests out of the box, which is all a test
// runner needs (no fast-refresh). The `@/*` path alias mirrors tsconfig so tests import the
// same way the app does.
const rootDir = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  resolve: {
    alias: { "@": rootDir.replace(/\/$/, "") },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules", ".next"],
    restoreMocks: true,
  },
});
