# Build guide

[Home](README_EN.md) · [Development (Chinese)](../zh/develop_guide.md) · [简体中文](../zh/build_guide.md)

## Environment and command

Build on Windows x64 with uv, a supported Python version, `7z` on PATH and the .NET Framework C# compiler `csc.exe`. The host builder searches PATH and the Windows Framework/Framework64 directories.

From the repository root:

```powershell
uv sync --frozen
uv run python .\scripts\build.py --version dev
```

The script cleans and recreates build output; do not store personal data in `dist/`. It builds the native Desktop Clone host, packages the application and updater, processes resources/translations, writes versions and manifests, and creates the archive and SHA-256.

## Outputs

| Path | Content |
| --- | --- |
| `dist/AALC/` | Complete runnable application |
| `dist/AALC/AALC.exe` | Main executable |
| `dist/AALC/AALC Updater.exe` | Updater |
| `dist/AALC/_internal/desktop_clone/AALC.DesktopCloneHost.exe` | Native Desktop Clone host |
| `dist/AALC_dev.7z` | Flat release archive |
| `dist/AALC_dev.7z.sha256` | Archive checksum |
| `dist/AALC.update_manifest.json` | Release-side update manifest |

The embedded manifest is `update_manifest.json`; the managed-file list is `managed_files.txt`. Use `dev` for local builds and the full matching tag version for releases.

## Release conventions

Current Canary packages use a flat layout and bootstrap protocol version 2. Maintain `assets/config/version.txt` and `CHANGELOG.md`; the GitHub Release body shown by the updater must match the changelog.

See [release.yaml](../../../.github/workflows/release.yaml) and [reusable-build.yml](../../../.github/workflows/reusable-build.yml). Verify the build SHA, Pre-release flag, unique archive, manifest, checksum and embedded version after publication.

Do not edit generated manifests manually or use the historical `--bridge-updater` option for ordinary Canary releases. Running PyInstaller specs alone does not prepare the native host or produce all release resources and metadata.

Keep build-script console output ASCII-safe for Windows CI environments using cp1252.
