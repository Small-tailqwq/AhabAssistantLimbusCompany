---
name: aalc-automation-practices
description: Apply AALC-specific conventions when implementing, debugging, or reviewing desktop automation, image or template matching, task orchestration, cooperative stopping, PySide6 UI, configuration, debug switches, or code structure in AhabAssistantLimbusCompany.
---

# AALC Automation Practices

Before editing, read the target signature, callers, and similar repository implementations. Do not impose generic software-design preferences on desktop automation behavior that has been tuned against a real UI.

## Load by task

- For `auto.*`, `ImageUtils.*`, OCR, UI location, retries, or automation flow, read [references/automation-design.md](references/automation-design.md).
- For task threads, start/stop, emulator waits, PySide6 UI, language/theme, or config, read [references/lifecycle-ui.md](references/lifecycle-ui.md).
- For replaying a user screenshot, load `replay-matching` and its production-pipeline reference.
- Before adding or changing `debug_*`, also read `.opencode/tools/debug_model_constitution.md`.

Load only the matching reference.

## Core workflow

1. Establish the real failure state, UI hierarchy, and call chain.
2. Inspect API defaults, search regions, template cropping, and similar code.
3. Choose the smallest change that explains the root cause; do not stack parameters as trial and error.
4. Keep the call graph flat unless a realistic reuse or semantic boundary justifies an abstraction.
5. Run the most relevant syntax, lint, test, or replay verification.
6. Review whether the diff is more complex than the failure and remove redundancy introduced by the change.

## Constraints

- Do not re-instantiate project singletons.
- Do not use user `config.yaml` as a template or synchronization target.
- Do not replace cooperative stopping with forced thread termination.
- Do not present general image-matching heuristics as facts without replay evidence.
- Do not change unrelated legacy code.
