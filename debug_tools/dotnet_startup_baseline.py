"""Measure source/desktop startup with isolated settings and explicit timing boundaries."""

from __future__ import annotations

import argparse
import ast
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def python_worker(output: Path, profile: Path, watcher: bool) -> None:
    started = time.perf_counter()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    sys.argv = [str(ROOT / "main.py")]
    import module

    profile.mkdir(parents=True, exist_ok=True)
    for name, relative in {
        "CONFIG_PATH": "config.yaml",
        "CONFIG_BACKUP_PATH": "config_backup",
        "THEME_PACK_LIST_PATH": "theme_pack_list.yaml",
        "THEME_PACK_WEIGHT_PATH": "theme_pack_weight",
        "LOG_DIR": "logs",
    }.items():
        setattr(module, name, str(profile / relative))

    # The copied profile is disposable; the application's singleton is still created once.
    import shutil

    config_source = ROOT / "config.yaml"
    shutil.copy2(config_source if config_source.exists() else ROOT / module.EXAMPLE_PATH, profile / "config.yaml")
    os.environ["AALC_DEV_MODE"] = "1"
    if watcher:
        from types import SimpleNamespace

        from main_dev import FileChangeHandler

        imported = time.perf_counter()
        FileChangeHandler(SimpleNamespace())
        ready = time.perf_counter()
        output.write_text(json.dumps({
            "kind": "python-watcher-component", "readyMonotonicSeconds": ready,
            "importSeconds": imported - started, "watcherScanSeconds": ready - imported,
            "profile": str(profile), "measurement": "imports plus initial content hashes; no app child",
        }, indent=2), encoding="utf-8")
        return

    import builtins

    original_import = builtins.__import__
    import_times = {}
    observed_names = {"app.my_app", "module.automation", "module.ocr", "rapidocr", "onnxruntime", "cv2", "qfluentwidgets"}

    def measured_import(name, *args, **kwargs):
        measure = name in observed_names and name not in sys.modules
        before = time.perf_counter() if measure else 0
        try:
            return original_import(name, *args, **kwargs)
        finally:
            if measure:
                import_times[name] = time.perf_counter() - before

    builtins.__import__ = measured_import
    import pyuac

    # UAC interaction is outside the developer launch budget, as in main_dev.py.
    pyuac.isUserAdmin = lambda: True

    def probe_exec(app, window):
        from PySide6.QtCore import QEvent, QObject, QTimer

        class FirstPaint(QObject):
            reported = False

            def eventFilter(self, watched, event):
                if watched is window and event.type() == QEvent.Type.Paint and not self.reported:
                    self.reported = True
                    QTimer.singleShot(0, report)
                return False

        def report():
            ready = time.perf_counter()
            output.write_text(json.dumps({
                "kind": "python-main", "readyMonotonicSeconds": ready,
                "workerSeconds": ready - started, "inclusiveImportsSeconds": import_times,
                "profile": str(profile), "windowVisible": window.isVisible(),
                "measurement": "main.py first paint followed by UI callback; UAC excluded; isolated copy of settings",
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            app.quit()

        observer = FirstPaint(window)
        window.installEventFilter(observer)
        window.update()
        return app.exec()

    with socket.socket() as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        port = probe_socket.getsockname()[1]

    class InstrumentEntry(ast.NodeTransformer):
        def visit_Constant(self, node):
            if node.value == 62333:
                return ast.copy_location(ast.Constant(port), node)
            return node

        def visit_Call(self, node):
            self.generic_visit(node)
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                if node.func.value.id == "app" and node.func.attr == "exec":
                    return ast.copy_location(ast.Call(ast.Name("probe_exec", ast.Load()), [
                        ast.Name("app", ast.Load()), ast.Name("ui", ast.Load())
                    ], []), node)
            return node

    source = ROOT / "main.py"
    tree = ast.fix_missing_locations(InstrumentEntry().visit(ast.parse(source.read_text(encoding="utf-8-sig"))))
    exec(compile(tree, str(source), "exec"), {"__name__": "__main__", "__file__": str(source), "probe_exec": probe_exec})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", choices=["python-main", "python-watcher", "desktop"], default="python-main")
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--output", type=Path, default=ROOT / "logs/dotnet_milestone_debug/startup.json")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()
    if args.worker:
        python_worker(args.output.resolve(), args.profile.resolve(), args.entry == "python-watcher")
        return 0
    if args.repeat < 1 or args.timeout <= 0:
        parser.error("repeat and timeout must be positive")
    if args.entry == "desktop" and not args.executable:
        parser.error("--executable is required for desktop")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    run_dir = output.parent / f"startup-{args.entry}-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir()
    results = []
    for index in range(args.repeat):
        sample = run_dir / f"sample-{index + 1}.json"
        profile = run_dir / f"profile-{index + 1}"
        if args.entry == "desktop":
            command = [str(args.executable.resolve()), "--startup-report", str(sample), "--profile", str(profile), "--exit-after-ready"]
        else:
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--entry", args.entry,
                       "--output", str(sample), "--profile", str(profile)]
        with (run_dir / f"sample-{index + 1}.log").open("w", encoding="utf-8") as log:
            launched = time.perf_counter()
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                exit_code = process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                parser.exit(1, f"Startup timed out; see {log.name}\n")
        if exit_code != 0 or not sample.exists():
            parser.exit(1, f"Startup failed ({exit_code}); see {log.name}\n")
        row = json.loads(sample.read_text(encoding="utf-8-sig"))
        row["launchToReadySeconds"] = row["readyMonotonicSeconds"] - launched
        results.append(row)
        sys.stdout.write(f"{args.entry} sample {index + 1}: {row['launchToReadySeconds']:.3f}s\n")
        sys.stdout.flush()
    report = {"entry": args.entry, "osCache": "uncontrolled; new process per sample, no reboot", "samples": results}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.write(f"Report: {output}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
