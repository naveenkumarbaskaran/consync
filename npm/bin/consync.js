#!/usr/bin/env node
/**
 * consync CLI wrapper for npm
 *
 * This delegates to the Python `consync` package. It attempts to find
 * the installed Python consync CLI and passes all arguments through.
 *
 * Install the Python package: pip install consync
 * Or use npx: npx consync sync
 */

const { execFileSync, execSync } = require("child_process");
const path = require("path");

const args = process.argv.slice(2);

// Try to find consync in PATH (installed via pip)
function findConsync() {
  const candidates = ["consync", "python3 -m consync", "python -m consync"];

  for (const cmd of candidates) {
    try {
      const parts = cmd.split(" ");
      if (parts.length === 1) {
        execSync(`which ${cmd}`, { stdio: "ignore" });
        return { cmd: parts[0], args: [] };
      } else {
        execSync(`${parts[0]} -c "import consync"`, { stdio: "ignore" });
        return { cmd: parts[0], args: parts.slice(1) };
      }
    } catch {
      continue;
    }
  }
  return null;
}

const found = findConsync();

if (!found) {
  console.error(`
Error: consync Python package not found.

Install it with:
  pip install consync

Or install Python 3.10+ and run:
  pip3 install consync

Then retry: npx consync sync
`);
  process.exit(1);
}

try {
  const result = execFileSync(found.cmd, [...found.args, ...args], {
    stdio: "inherit",
    env: process.env,
  });
} catch (err) {
  process.exit(err.status || 1);
}
