---
name: Python package setup in imported Repls
description: A Replit package-installation mismatch observed in this Python 3.12 import.
---

In this imported Python environment, the package installer implicitly uses pip's user install mode, which can fail even when the interactive interpreter reports user-site support. The supported package-install callback failed, and adding Python packages through Nix did not make them importable by the active interpreter.

**Why:** A successful package-manager response did not guarantee the app's Python process could import the dependency.

**How to apply:** Try the supported package-install callback first. If this specific user-site failure recurs, the verified fallback is pip with explicit `--no-user --target .pythonlibs/lib/python3.12/site-packages -r requirements.txt`, retaining the configured package firewall. The active interpreter already searches that target. Verify imports before claiming success, and keep installed dependencies out of Git.

The same user-site failure also occurs in publishing's automatic dependency install, before a custom build command runs. The platform's pip configuration sets `user = yes`. Publishing still ran its automatic installer despite `packager.features.enabledForHosting = false`; do not assume that setting bypasses this stage.

**Why:** Installing packages successfully in the development workspace does not fix the separate dependency-install stage used by publishing. A custom build alone cannot repair a stage that fails before reaching it.

**How to apply:** Shared `PIP_USER=false` and `PIP_TARGET=.pythonlibs/lib/python3.12/site-packages` make the exact `pip install -r requirements.txt` command succeed locally, including a disabled-user-site dry run. However, another production publish still failed with the identical user-install error even though those overrides were saved and visible in production environment metadata. These settings are not a verified publishing fix. Do not ask for another unchanged retry or claim that local success proves publishing is repaired; the remaining automatic-installer behavior needs investigation beyond the available build logs.
