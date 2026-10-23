---
name: Python packaging with uv
description: Why this project uses uv instead of the failing automatic pip flow.
---

Use the uv project flow for this app rather than reintroducing root requirements.txt or pip-settings workarounds.

**Why:** The user explicitly requested switching to uv after repeated publishing failures in automatic pip installation. A custom build command, disabling hosting installation, and shared pip overrides all failed to resolve that stage, even though local installs succeeded.

**How to apply:** Manage dependencies through pyproject.toml and uv.lock and let publishing perform its uv installation without a custom deployment build command. Do not resume patching pip settings to address this issue. Verify the locked install locally, and distinguish local verification from an actual successful production publish.
