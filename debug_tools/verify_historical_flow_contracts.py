"""离线核验历史 PR 中的流程契约；仅提取 Git 源码，不导入 AALC 运行时。"""

import ast
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def source(revision, path):
    return subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout


def function(text, name):
    return next(node for node in ast.walk(ast.parse(text)) if isinstance(node, ast.FunctionDef) and node.name == name)


def default(node, name):
    pairs = zip(node.args.args[-len(node.args.defaults) :], node.args.defaults)
    return ast.literal_eval(next(value for arg, value in pairs if arg.arg == name))


def retry_probe(revision, skip):
    node = function(source(revision, "tasks/base/retry.py"), "retry")
    observations = {"captures": 0, "iterations": 0}
    auto = SimpleNamespace(screenshot="connecting", get_restore_time=lambda: None)

    def capture():
        observations["captures"] += 1
        auto.screenshot = "clear"
        return auto.screenshot

    def check_times(start):
        observations["iterations"] += 1
        return observations["iterations"] > 3

    auto.take_screenshot = capture
    auto.find_element = lambda key, **kw: (key == "base/connecting_assets.png" and auto.screenshot == "connecting")
    auto.click_element = lambda *args, **kw: False
    namespace = {
        "auto": auto,
        "screen": SimpleNamespace(handle=SimpleNamespace(hwnd=1)),
        "time": SimpleNamespace(time=lambda: 0),
        "check_times": check_times,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<historical-retry>", "exec"), namespace)
    result = namespace["retry"](**({"skip_screenshot": skip} if skip is not None else {}))
    return {**observations, "result": result}


def refresh_predicates(revision):
    node = function(source(revision, "tasks/mirror/in_shop.py"), "buy_gifts")
    allowed = {"self", "my_remaining_money", "keyword_refresh_count", "normal_refresh_count"}
    routes = []

    def walk(node, conditions=()):
        if isinstance(node, ast.If):
            walk(node.test, conditions)
            names = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
            relevant = "my_remaining_money" in names or bool(names & {"keyword_refresh_count", "normal_refresh_count"})
            include = relevant and names <= allowed
            for child in node.body:
                walk(child, conditions + ((node.test,) if include else ()))
            for child in node.orelse:
                negative = ast.UnaryOp(op=ast.Not(), operand=node.test)
                walk(child, conditions + ((negative,) if include else ()))
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "click_element" and node.args and isinstance(node.args[0], ast.Constant):
                key = node.args[0].value
                if key in {"mirror/shop/refresh_assets.png", "mirror/shop/refresh_keyword_assets.png"}:
                    routes.append((key, conditions))
        for child in ast.iter_child_nodes(node):
            walk(child, conditions)

    walk(node)
    output = {}
    for money in [-1, 0, 199, 200, 299, 300]:
        namespace = {
            "self": SimpleNamespace(max_keyword_refresh=2, max_normal_refresh=2),
            "my_remaining_money": money,
            "keyword_refresh_count": 0,
            "normal_refresh_count": 0,
        }
        output[money] = [
            key
            for key, conditions in routes
            if all(
                eval(compile(ast.fix_missing_locations(ast.Expression(test)), "<predicate>", "eval"), namespace)
                for test in conditions
            )
        ]
    return output


def main():
    old_retry = retry_probe("8aa21f20bc224a9c0b3f92149fcfecb2f9bc73c9", True)
    new_retry = retry_probe("9958fc3f6dedb7a30d6710dfa3f416311cd38d35", None)
    assert old_retry == {"captures": 0, "iterations": 4, "result": False}
    assert new_retry == {"captures": 1, "iterations": 1, "result": None}

    old_shop = refresh_predicates("51798089")
    new_shop = refresh_predicates("dbf8a9ce3e58176298bc4e4f900febd0155b1420")
    assert old_shop[-1] and not new_shop[-1]
    normal = "mirror/shop/refresh_assets.png"
    assert old_shop[200].count(normal) == 2 and new_shop[200].count(normal) == 1

    revision = "094de9607199a0edeaad6a3ba79834f4c94f0e89"
    api = function(source(revision, "module/automation/automation.py"), "find_element")
    threshold = default(api, "threshold")
    text = source(revision, "tasks/daily/luxcavation.py")
    consume = [
        n
        for n in ast.walk(ast.parse(text))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "find_element"
        and not any(k.arg == "find_type" for k in n.keywords)
        and n.args
        and isinstance(n.args[0], ast.Constant)
        and n.args[0].value == "luxcavation/thread_consume.png"
    ]
    assert len(consume) == 2 and threshold == 0.8
    assert all(not any(k.arg == "threshold" for k in n.keywords) for n in consume)

    api = function(
        source("fb4f607ff4f69257789bddfe02fafae6d4eef879", "module/automation/automation.py"), "click_element"
    )
    assert default(api, "model") is None
    resolution = next(n for n in api.body if isinstance(n, ast.If) and ast.unparse(n.test) == "model is None")
    inherited = {"model": None, "self": SimpleNamespace(model="aggressive")}
    explicit = {"model": "clam", "self": SimpleNamespace(model="aggressive")}
    code = compile(ast.Module(body=[resolution], type_ignores=[]), "<model-resolution>", "exec")
    exec(code, inherited)
    exec(code, explicit)
    assert inherited["model"] == "aggressive" and explicit["model"] == "clam"

    sys.stdout.write(
        json.dumps(
            {
                "retry_677_to_683": {"before": old_retry, "after": new_retry},
                "shop_675": {"before": old_shop, "after": new_shop},
                "threshold_762": {"effective": threshold, "calls_using_default": len(consume)},
                "mutable_model_counterexample": {"omitted": inherited["model"], "explicit": explicit["model"]},
                "boundary": "Synthetic observations and extracted predicates; no game, OCR, screenshots, or timing validation.",
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
