// Shared by the function tests. Not a test file itself.
import { cpSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

/** Copies functions/ into parent/name with a package.json marking it as ES modules; returns the folder. */
export function copyFunctions(parent, name) {
  const target = join(parent, name);
  mkdirSync(target, { recursive: true });
  cpSync(join(here, "..", "..", "functions"), target, { recursive: true });
  writeFileSync(join(target, "package.json"), '{"type":"module"}');
  return target;
}
