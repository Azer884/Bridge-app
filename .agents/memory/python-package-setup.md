---
name: Python package setup in imported Repls
description: A Replit package-installation mismatch observed in this Python 3.12 import.
---

In this imported Python environment, the package installer implicitly uses pip's user install mode, which can fail even when the interactive interpreter reports user-site support. The supported package-install callback failed, and adding Python packages through Nix did not make them importable by the active interpreter.

**Why:** A successful package-manager response did not guarantee the app's Python process could import the dependency.

**How to apply:** Try the supported package-install callback first. If this specific user-site failure recurs, the verified fallback is pip with explicit `--no-user --target .pythonlibs/lib/python3.12/site-packages -r requirements.txt`, retaining the configured package firewall. The active interpreter already searches that target. Verify imports before claiming success, and keep installed dependencies out of Git.
