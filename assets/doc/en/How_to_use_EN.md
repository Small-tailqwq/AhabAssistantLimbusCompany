# Getting started

[Home](README_EN.md) · [FAQ](FAQ_EN.md) · [Configuration](Custom_setting_EN.md) · [简体中文](../zh/How_to_use.md)

This guide describes the experimental CanaryAssistant fork.

## Install and update

1. Download `AALC_<version>.7z` from a Pre-release in [this repository](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/releases). GitHub's Source code archives are not Windows application packages.
2. Extract everything into a writable directory and run `AALC.exe`. Keep `_internal/`, `assets/` and the updater alongside it.
3. The packaged `AALC.exe` requests administrator rights. Check the game path, game language and window resolution in Settings.
4. Before updating, stop tasks and back up `config.yaml`, `theme_pack_list.yaml` and `theme_pack_weight/`. Do not overwrite personal settings with example configuration files.

Canary-channel builds and versions containing `-canary` check this fork for updates. The ordinary Stable path uses upstream stable releases; it is not a stable edition of this fork. If an update fails, keep the logs and download the intended version manually.

## First run

1. Confirm that the game can log in and reach its home screen, the selected stages are unlocked, and your team can clear them.
2. Match the configured game language and resolution to the actual game. Application language is a separate setting. Check that captured frames are complete and correctly proportioned.
3. Select tasks, teams, run counts, Lunacy spending and completion actions.
4. Keep default timing and disable optional experiments initially. Observe a short run before extending it.
5. If it stalls or clicks incorrectly, pause or stop, preserve the game screenshot and logs, then follow the FAQ.

## Task controls

| Action | Default shortcut |
| --- | --- |
| Request a task stop | `Ctrl+Q` |
| Pause or resume | `Alt+P` / `Alt+R` |

Shortcuts are configurable. Stopping requests cooperative cleanup; it does not forcibly kill the application. Wait until the task ends and controls return to idle. If shortcuts fail, use the UI controls and check focus, input mode and privileges.

<details>
<summary>Emulators</summary>

Enable emulator mode and configure the actual emulator type, instance and connection details. MuMu has a dedicated integration; other types use an ADB path. Read the port from your current instance instead of copying a fixed port from an old guide.

Match the emulator resolution to AALC, check ADB debugging, and inspect MuMu application keep-alive settings if frames are stale or blank. Include emulator version, instance and connection logs in reports.

</details>

<details>
<summary>Background input and Desktop Clone</summary>

Background input still depends on a usable game window and capture in the current session. Minimized windows, a locked desktop and remote-session changes are not guaranteed to work.

Desktop Clone is off by default. It runs tasks in a separate Windows Child Session and requires administrator rights and a compatible Remote Desktop environment. Windows Home is outside the initial support scope, and emulator mode cannot be combined with it. Run the toolbox compatibility check first. The main controller manages tasks and synchronized logs; the clone window exposes audio/input controls. Use the provided stop-and-log-off action when finished.

</details>

<details>
<summary>Start saved tasks from the command line</summary>

From the application directory:

```powershell
.\AALC.exe start
.\AALC.exe start --exit
```

`start` runs saved tasks; `--exit` without a value exits AALC after completion. Check task counts and completion actions before using it. Other compatibility arguments are parsed by `app/my_app.py::command_start`; old dropdown indices are not a description of the current UI.

</details>
