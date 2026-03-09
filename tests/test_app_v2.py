import sys
import threading
import time

from yaml_cli_ui.app_v2 import launcher_param_plan, resolve_profile_ui_state, run_launcher
from yaml_cli_ui.v2.loader import load_v2_document


def _write_doc(tmp_path, text: str):
    path = tmp_path / "app_v2.yaml"
    path.write_text(text, encoding="utf-8")
    return load_v2_document(path)


def test_app_v2_loads_minimal_document_and_launchers(tmp_path):
    doc = _write_doc(
        tmp_path,
        """
version: 2
commands:
  hello:
    run:
      program: python
      argv: ["-c", "print('ok')"]
launchers:
  main:
    title: Main launcher
    info: demo
    use: hello
""",
    )
    assert "main" in doc.launchers
    assert doc.launchers["main"].title == "Main launcher"
    assert doc.launchers["main"].info == "demo"


def test_profile_selector_states(tmp_path):
    doc_none = _write_doc(tmp_path, "version: 2\nlaunchers: {l: {title: L, use: c}}\ncommands: {c: {run: {program: python}}}\n")
    assert resolve_profile_ui_state(doc_none) == (False, None, [])

    doc_one = _write_doc(tmp_path, "version: 2\nprofiles: {dev: {}}\nlaunchers: {l: {title: L, use: c}}\ncommands: {c: {run: {program: python}}}\n")
    assert resolve_profile_ui_state(doc_one) == (False, "dev", ["dev"])

    doc_many = _write_doc(tmp_path, "version: 2\nprofiles: {a: {}, b: {}}\nlaunchers: {l: {title: L, use: c}}\ncommands: {c: {run: {program: python}}}\n")
    show, selected, names = resolve_profile_ui_state(doc_many)
    assert show is True
    assert selected == "a"
    assert names == ["a", "b"]


def test_launcher_param_plan_with_fixed_bindings(tmp_path):
    doc = _write_doc(
        tmp_path,
        """
version: 2
params:
  token: {type: secret}
  mode: {type: string, required: true}
commands:
  hello:
    run:
      program: python
launchers:
  l:
    title: L
    use: hello
    with:
      mode: fixed
""",
    )
    editable, fixed = launcher_param_plan(doc, "l")
    assert "mode" not in editable
    assert "token" in editable
    assert fixed == {"mode": "fixed"}


def test_run_launcher_executes_v2_and_background_thread(tmp_path):
    doc = _write_doc(
        tmp_path,
        f"""
version: 2
commands:
  sleeper:
    run:
      program: {sys.executable}
      argv: ["-c", "import time; time.sleep(0.15); print('ok')"]
launchers:
  l:
    title: L
    use: sleeper
""",
    )
    result_holder = {}

    def worker():
        result_holder["result"] = run_launcher(doc, launcher_name="l", params={})

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.03)
    assert t.is_alive()
    t.join(timeout=1)
    assert result_holder["result"].status.value == "success"
