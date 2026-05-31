import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import React from "react";

(globalThis as typeof globalThis & { React: typeof React }).React = React;

if (typeof window !== "undefined" && typeof window.URL.createObjectURL !== "function") {
  window.URL.createObjectURL = () => "blob:mock-url";
}

// Cleanup after each test
afterEach(() => {
  cleanup();
});
