---
name: Python packaging with uv
description: Why this project uses uv instead of the failing automatic pip flow.
---

Use the uv project flow for this app rather than reintroducing root requirements.txt or pip-settings workarounds.

**Why:** The user explicitly requested switching to uv after repeated publishing failures in automatic pip installation. A custom build command, disabling hosting installation, and shared pip overrides all failed to resolve that stage, even though local installs succeeded.

**How to apply:** Manage dependencies through pyproject.toml and uv.lock and let publishing perform its uv installation without a custom deployment build command. Do not resume patching pip settings to address this issue. Verify the locked install locally, and distinguish local verification from an actual successful production publish.

Let uv own the project environment; do not install packages into `.pythonlibs` using `--target`.

**Why:** Earlier target installs left a package-only directory without a Python executable or environment configuration. Publishing advanced past locking but `uv sync` rejected that directory. An export-and-target install was therefore not a valid substitute for testing the publishing flow.

**How to apply:** Verify with actual `uv lock` and `uv sync`. If the confirmed stale package-only environment is still present, remove only that generated directory and let uv recreate it. Keep it ignored and untracked. A clean sync and `uv sync --check` succeeded after this cleanup; do not recreate the package-only layout.
