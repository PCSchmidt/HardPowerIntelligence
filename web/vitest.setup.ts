// Extends Vitest's `expect` with @testing-library/jest-dom matchers (toBeInTheDocument,
// toHaveTextContent, …) and registers their types globally. Also resets the jsdom DOM and
// localStorage between tests so component tests don't leak state into one another.
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
