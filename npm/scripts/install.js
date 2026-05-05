/**
 * Post-install script — checks if Python consync is available
 * and provides helpful instructions if not.
 */

const { execSync } = require("child_process");

function check() {
  try {
    const version = execSync("consync --version", { encoding: "utf-8" }).trim();
    console.log(`✔ consync found: ${version}`);
    return;
  } catch {}

  try {
    const version = execSync("python3 -m consync --version", { encoding: "utf-8" }).trim();
    console.log(`✔ consync found (via python3 -m): ${version}`);
    return;
  } catch {}

  console.log(`
┌─────────────────────────────────────────────────┐
│  consync npm wrapper installed successfully     │
│                                                 │
│  ⚠️  Python package not found yet.              │
│  Install it with: pip install consync           │
│                                                 │
│  Requires Python 3.10+                          │
└─────────────────────────────────────────────────┘
`);
}

check();
