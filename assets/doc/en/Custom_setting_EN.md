# Configuration

[Home](README_EN.md) · [Getting started](How_to_use_EN.md) · [简体中文](../zh/Custom_setting.md)

## Daily tasks and rewards

Task selection and task parameters are separate. Check EXP/Thread counts, teams, day-specific team choices, Lunacy refills and completion actions. Mail, daily/weekly missions and pass-level rewards are separate reward options.

## Mirror Dungeon teams

Enable teams and arrange their execution order. Confirm the in-game team index or name-selection method. Each team can configure gift systems, Sinner order, shop strategies and theme-pack weights.

Hard mode, weekly bonuses, early exit, saved rewards and unlimited runs affect the actual workflow. Start with a finite run and verify team and reward behavior first.

## Theme-pack weights

Use the graphical settings page. Higher values mean higher preference among candidates, subject to refresh thresholds, available refreshes and other strategies. Low weight is not a guarantee that a pack will never be selected.

- Global weights and team-specific overrides are stored separately.
- “Unknown” sets the fallback for unrecognized packs.
- C24 updated localized keywords, rerun weights and railway entries.
- Synchronization retains keywords still present in the default catalog. Removed or custom legacy keywords may be discarded; review custom weights after upgrading.

<details>
<summary>Configuration files</summary>

| File | Purpose |
| --- | --- |
| `config.yaml` | General settings, tasks and teams |
| `theme_pack_list.yaml` | Global theme-pack catalog and weights |
| `theme_pack_weight/theme_pack_weight_team_<number>.yaml` | Team-specific weights |
| `assets/config/config.example.yaml` | Shipped configuration defaults |

Stop tasks and back up before editing. Do not overwrite personal configuration with examples or commit credentials. Desktop Clone has separate configuration and log scopes.

</details>

## Input, capture and experiments

PC mode supports foreground/background input. Logitech/Razer input needs its own DLL and environment; OBS capture needs a reachable WebSocket service and the correct game capture source. These are optional.

Desktop Clone is off by default; run its compatibility check first. Change one relevant setting at a time so failures can be traced.

Debug switches save evidence for specific workflows, usually under `logs/`. Enable only the needed switches; turning off the parent debug mode resets its child switches.
