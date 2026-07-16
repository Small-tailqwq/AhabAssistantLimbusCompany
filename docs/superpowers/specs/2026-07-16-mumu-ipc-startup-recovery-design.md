# MuMu IPC Startup Recovery Design

## Scope

Repair the MuMu startup path exposed by a released upstream build when the
emulator manager reports incomplete startup and Nemu IPC is not yet ready.
The change is limited to `mumu_control.py` and its focused unit tests.

## Failure Chain

The existing startup flow waits for the manager state, but continues after a
timeout and immediately calls Nemu IPC. A failed `nemu_connect` enters the
fallback path, where standard-stream capture can corrupt the Python stream
object and raise `AttributeError` for `fileno`. The fallback then recursively
restarts the emulator without a bounded recovery condition.

## Design

`MumuControl.start()` will treat a successful Nemu IPC connection as the
readiness criterion. It will poll the manager state until the configured
startup deadline, try IPC only after the manager reports `start_finished`, and
retry transient IPC failures within that same deadline. It will raise one
descriptive `RuntimeError` at the deadline instead of recursively restarting.

The stream capture context manager will preserve the original Python stream
objects while redirecting and restoring the underlying file descriptors. This
allows a failed Nemu IPC call to emit its diagnostic output without making
`sys.stdout` or `sys.stderr` unusable.

Startup retry diagnostics are logged at debug level to avoid reporting normal
IPC warm-up as an application failure.

## Tests

Focused unit tests cover:

- transient IPC connection failures that recover before the configured
  deadline;
- IPC failures that reach the deadline and retain the underlying cause;
- debug-level routing of retry diagnostics.

The existing MuMu input retry tests remain unchanged in intent.

## Non-Goals

- Do not change MuMu installation detection or version requirements.
- Do not add new configuration fields or alter the configured startup timeout.
- Do not change emulator launch commands, instance selection, or game startup.
