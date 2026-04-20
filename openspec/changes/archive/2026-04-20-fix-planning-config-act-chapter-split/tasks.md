## 1. Fix autopilot_daemon structure_preference extraction

- [x] 1.1 Add `structure` field unwrapping in `_generate_macro_plan_if_needed`

Priority: extract from `planning_config.structure` if exists, else fallback to top-level attributes.
