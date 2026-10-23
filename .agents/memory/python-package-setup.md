---
name: Python package setup in imported Repls
description: A Replit package-installation mismatch observed in this Python 3.12 import.
---

In this imported Python 3.12 environment, `installLanguagePackages` attempted a pip user install and failed because user site-packages were disabled for that installer process. Installing `python312Packages.*` through the Nix dependency route reported success but did not make FastAPI importable from the active Python interpreter.

**Why:** A successful package-manager response did not guarantee the app's Python process could import the dependency.

**How to apply:** Verify required imports with the active interpreter before claiming Python dependencies are installed. Don't leave Nix Python package entries in `.replit` if the active interpreter still cannot import them.
