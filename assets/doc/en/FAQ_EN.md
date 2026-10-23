# FAQ

[Home](README_EN.md) · [Getting started](How_to_use_EN.md) · [简体中文](../zh/FAQ.md)

## It stalls, misclicks or cannot recognize a screen

Pause and save the original game screenshot and logs at the failure time. Check game language, resolution, window bounds and the current page. HDR, night mode, overlays, fonts and game UI changes can affect recognition.

Identify the active capture and input paths. Test optional OBS, Logitech/Razer and Desktop Clone features separately instead of changing every setting at once.

## The window is visible but input does not work

Check the privilege levels of AALC, the game and any external controller, plus the selected input mode. The packaged `AALC.exe` requests elevation. Source entry points `main.py` and `main_dev.py` inherit the terminal's privileges; use an administrator terminal to run Desktop Clone from source. A privilege mismatch is a possible cause to verify, not a diagnosis by itself.

If driver input is enabled, check the driver and DLL configuration; disable that path when it is not configured. For keyboard failures, also check the input method and keyboard focus.

## Can it run in the background?

There is background input and a separate experimental Desktop Clone mode. Background input does not guarantee operation while minimized, locked or switching remote sessions. Desktop Clone has additional compatibility requirements. See the [usage guide](How_to_use_EN.md).

## Why were rewards not collected?

Check selected reward actions, completed progress, claimable rewards and whether the pass page opens. C24 fixed pass-entry search bounds and completed-mission background recognition. If it recurs, include both the entry screen and the rewards page; a finished log sequence alone is not proof of collection.

## Can I avoid a Mirror Dungeon theme pack?

Lower its weight in the theme-pack UI and check any team-specific override. Weights control preference, not an absolute ban. Unrecognized packs use the “unknown” fallback; rerun and original packs can share weights. See [configuration](Custom_setting_EN.md).

## Updates fail or downloads are slow

Use [this fork's Releases](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/releases), and check network access and update proxy settings. The current download path uses GitHub; inherited instructions for a paid distribution service do not describe this fork's current updater. A complete package can be downloaded manually while preserving personal configuration and logs.

## Emulator startup fails or captures do not refresh

Check the emulator type, instance, actual ADB port, debugging state and resolution. For MuMu, also inspect application keep-alive and reconnection logs. Recovery code does not mean every emulator version has been validated.

## What should a bug report include?

Open an issue in [this repository](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/issues) with:

- AALC version or commit, game language, resolution and Windows version.
- PC/emulator/Desktop Clone mode, input method and capture method.
- Selected tasks, expected and actual results, first failure timestamp and reproduction steps.
- Logs around the failure and uncropped game screenshots at their original resolution.

Remove account details, personal information and credentials before sharing. Do not upload an unredacted full configuration file.
