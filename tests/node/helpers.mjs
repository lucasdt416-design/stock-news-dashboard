// Shared by the function tests. Not a test file itself.
import { cpSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
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

/** Loads one of the page's plain script files (pipeline/portfolio_*.js) and returns the object it defines. */
export function loadPageScript(file, name) {
  const source = readFileSync(join(here, "..", "..", "pipeline", file), "utf8");
  return new Function(`${source}\nreturn ${name};`)();
}
