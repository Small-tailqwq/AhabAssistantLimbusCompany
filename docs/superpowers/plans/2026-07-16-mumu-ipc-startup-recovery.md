# MuMu IPC Startup Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent MuMu startup from crashing or recursively restarting when Nemu IPC becomes ready after the manager process.

**Architecture:** Preserve Python stream objects while temporarily redirecting their Windows file descriptors for Nemu IPC diagnostics. Make `MumuControl.start()` wait for both manager startup state and a successful Nemu IPC connection within the existing timeout; report one bounded failure otherwise.

**Tech Stack:** Python 3.12, `asyncio`, `ctypes`, `unittest`, MuMu12 Nemu IPC DLL.

## Global Constraints

- Windows-only desktop automation; preserve cooperative stopping through `check_stop_requested()`.
- Do not add configuration or alter `cfg.start_emulator_timeout` semantics.
- Do not change MuMu version detection, installation discovery, launch command, or instance selection.
- Keep the upstream patch limited to `module/automation/input_handlers/simulator/mumu_control.py` and `tests/test_mumu_ipc_retry.py`.

---

### Task 1: Preserve IPC Diagnostic Streams

**Files:**
- Modify: `module/automation/input_handlers/simulator/mumu_control.py:110-141, 668-735`
- Test: `tests/test_mumu_ipc_retry.py:98-121`

**Interfaces:**
- Consumes: a failing C IPC function invoked by `ev_run_sync()`.
- Produces: `connect(*, log_level="warning") -> None` and diagnostic output at
  the supplied log level without replacing Python's original stream objects.

- [ ] **Step 1: Write the failing retry-diagnostic test**

Add a test that creates `CaptureNemuIpc` with `log_level="debug"`, supplies
Nemu IPC stderr, and asserts it is emitted through `LoggerStub.debug`:

```python
capture = mumu_control_module.CaptureNemuIpc(LoggerStub(), log_level="debug")
capture.stderr = b"nemu_connect instance_name: pending"
capture.check_stderr()

self.assertEqual(messages, [("debug", "NemuIpc stderr: b'nemu_connect instance_name: pending'")])
```

- [ ] **Step 2: Run the diagnostic test and verify it fails**

Run: `uv run python -m unittest tests.test_mumu_ipc_retry.TestMumuIpcInputRetry.test_capture_nemu_ipc_uses_debug_for_startup_retry_output -v`

Expected: FAIL because the upstream capture helper accepts no log level and
always records stderr as an error.

- [ ] **Step 3: Implement safe stream restoration and diagnostic routing**

Save the original Python stream objects before `os.dup2`; create replacement
wrappers only while capture is active; restore the saved objects before
restoring the duplicated file descriptors. Add `log_level` to
`CaptureNemuIpc`, `ev_run_sync`, and `connect`, then pass it through to the
diagnostic logger:

```python
self._saved_stdout = sys.stdout
self._saved_stderr = sys.stderr
os.dup2(self.writer_out, self.fdout)
os.dup2(self.writer_err, self.fderr)
sys.stdout = os.fdopen(self.fdout, "w")
sys.stderr = os.fdopen(self.fderr, "w")

# In __exit__
sys.stdout = self._saved_stdout
sys.stderr = self._saved_stderr
os.dup2(self.old_stdout, self.fdout)
os.dup2(self.old_stderr, self.fderr)
```

- [ ] **Step 4: Run the focused diagnostic tests and verify they pass**

Run: `uv run python -m unittest tests.test_mumu_ipc_retry.TestMumuIpcInputRetry.test_capture_nemu_ipc_uses_debug_for_startup_retry_output tests.test_mumu_ipc_retry.TestMumuIpcInputRetry.test_connect_forwards_startup_log_level_to_nemu_ipc -v`

Expected: both PASS.

### Task 2: Bound MuMu IPC Startup Readiness

**Files:**
- Modify: `module/automation/input_handlers/simulator/mumu_control.py:431-503`
- Test: `tests/test_mumu_ipc_retry.py:123-184`

**Interfaces:**
- Consumes: `cfg.start_emulator_timeout`, `get_launch_status() -> str`, and
  `connect(log_level="debug") -> None` from Task 1.
- Produces: `start() -> None` only after IPC connection succeeds; raises
  `RuntimeError` on deadline expiry.

- [ ] **Step 1: Write the failing recovery test**

Add a test that advances a mocked monotonic clock while `connect()` raises three
`NemuIpcError` values and then succeeds:

```python
connection_error = mumu_control_module.NemuIpcError("IPC 尚未就绪")
connect_results = [connection_error] * 3 + [None]

with patch.object(control, "get_launch_status", return_value="start_finished"), \
     patch.object(control, "connect", side_effect=connect_results) as connect:
    control.start()

assert connect.call_count == 4
assert all(call.kwargs == {"log_level": "debug"} for call in connect.call_args_list)
```

- [ ] **Step 2: Run the recovery test and verify it fails**

Run: `uv run python -m unittest tests.test_mumu_ipc_retry.TestMumuIpcInputRetry.test_start_retries_ipc_until_configured_timeout -v`

Expected: FAIL because the upstream startup flow calls `connect()` once after a
manager-state timeout and does not retry pending IPC.

- [ ] **Step 3: Write the failing deadline test**

Add a test with `start_emulator_timeout = 3` and a permanently failing
`connect()`. Assert the raised `RuntimeError` names the IPC readiness timeout
and keeps the final `NemuIpcError` as `__cause__`:

```python
with self.assertRaisesRegex(RuntimeError, "启动超时（3秒），等待 Nemu IPC 就绪") as raised:
    control.start()

self.assertIs(raised.exception.__cause__, connection_error)
```

- [ ] **Step 4: Run the deadline test and verify it fails**

Run: `uv run python -m unittest tests.test_mumu_ipc_retry.TestMumuIpcInputRetry.test_start_reports_timeout_after_ipc_deadline -v`

Expected: FAIL because the upstream fallback restarts recursively instead of
raising a deadline-bounded error.

- [ ] **Step 5: Implement bounded readiness polling**

Replace recursive fallback in `start()` with one deadline loop. Launch once,
load the IPC DLL and discover the ADB port once, poll manager state, then retry
only `NemuIpcError` and `asyncio.TimeoutError` until the deadline:

```python
deadline = time.monotonic() + cfg.start_emulator_timeout
seen_started_state = False
last_connection_error = None

while time.monotonic() < deadline:
    self.check_stop_requested()
    if self.get_launch_status() != "start_finished":
        time.sleep(min(1, max(0, deadline - time.monotonic())))
        continue
    seen_started_state = True
    try:
        self.connect(log_level="debug")
        return
    except (NemuIpcError, asyncio.TimeoutError) as error:
        last_connection_error = error
        time.sleep(min(1, max(0, deadline - time.monotonic())))

if seen_started_state:
    raise RuntimeError(f"Mumu模拟器启动超时（{cfg.start_emulator_timeout}秒），等待 Nemu IPC 就绪") from last_connection_error
raise RuntimeError(f"Mumu模拟器启动超时（{cfg.start_emulator_timeout}秒），未检测到启动完成状态")
```

- [ ] **Step 6: Run the focused MuMu test module and static validation**

Run: `uv run python -m unittest tests.test_mumu_ipc_retry -v`

Expected: all tests PASS.

Run: `uv run ruff check module/automation/input_handlers/simulator/mumu_control.py tests/test_mumu_ipc_retry.py`

Expected: exit code 0.

- [ ] **Step 7: Review and commit the isolated patch**

Run:

```bash
git diff --check
git diff -- module/automation/input_handlers/simulator/mumu_control.py tests/test_mumu_ipc_retry.py
git status --short
git add module/automation/input_handlers/simulator/mumu_control.py tests/test_mumu_ipc_retry.py
git commit -m "fix: 等待 MuMu IPC 就绪并修复启动重试"
```

Expected: one commit containing only the two planned files.
