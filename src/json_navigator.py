#!/usr/bin/env python3
# json_navigator.py
# Terminal JSON explorer/editor using Textual + Rich.
# - Collapsed key tree with "(...)" for leaves
# - Enter toggles branches; on leaves opens ops menu (Display / Base64 decode / Edit)
# - Edit uses $EDITOR and updates in-memory JSON
# - Reads from --in PATH or stdin
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, List, Tuple, Union

from rich.pretty import pretty_repr
from textual.app import App, ComposeResult
from textual.screen import ModalScreen
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Label, Tree, OptionList, Button
from textual.widgets.option_list import Option

# ---------- Log/TextLog/RichLog compatibility shim ----------

try:
  # Newer Textual
  from textual.widgets import Log as _LogWidget  # type: ignore
except Exception:
  try:
    # Older Textual
    from textual.widgets import TextLog as _LogWidget  # type: ignore
  except Exception:
    # Fallback (mid versions)
    from textual.widgets import RichLog as _LogWidget  # type: ignore

def _log_write_lines(w: Any, text: str) -> None:
  """Write lines to any of Log/TextLog/RichLog across versions."""
  for line in text.splitlines():
    if hasattr(w, "write"):
      w.write(line)
    elif hasattr(w, "write_line"):
      w.write_line(line)
    elif hasattr(w, "log"):
      w.log(line)
    else:
      try:
        w.lines.append(line)  # type: ignore[attr-defined]
      except Exception:
        pass

# ---------- Types ----------

JSONPrimitive = Union[str, int, float, bool, None]
JSONType = Union[dict, list, JSONPrimitive]
Path = Tuple[Union[str, int], ...]


# ---------- Utilities ----------

def read_json_from_args_or_stdin(path: str | None) -> JSONType:
  if path:
    with open(path, "r", encoding="utf-8") as f:
      return json.load(f)
  if sys.stdin.isatty():
    print("Error: no --in provided and stdin is TTY. Pipe JSON or use --in PATH.", file=sys.stderr)
    sys.exit(2)
  return json.load(sys.stdin)

def is_leaf(value: Any) -> bool:
  return not isinstance(value, (dict, list))

def path_to_str(path: Path) -> str:
  parts: List[str] = []
  for p in path:
    parts.append(f"[{p}]" if isinstance(p, int) else str(p))
  return ".".join(parts) if parts else "$"

def get_by_path(data: JSONType, path: Path) -> JSONType:
  cur: Any = data
  for p in path:
    cur = cur[p]
  return cur

def set_by_path(data: JSONType, path: Path, new_value: JSONType) -> None:
  if not path:
    raise ValueError("Refusing to overwrite root object")
  parent = get_by_path(data, path[:-1])
  parent[path[-1]] = new_value

def hexdump(b: bytes, width: int = 16, limit: int = 8192) -> str:
  b = b[:limit]
  lines = []
  for i in range(0, len(b), width):
    chunk = b[i:i+width]
    hexs = " ".join(f"{c:02x}" for c in chunk)
    text = "".join(chr(c) if 32 <= c < 127 else "." for c in chunk)
    lines.append(f"{i:08x}  {hexs:<{width*3}}  {text}")
  if len(b) == limit:
    lines.append("… (truncated)")
  return "\n".join(lines)

def open_in_editor(initial_text: str) -> str | None:
  editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
  if not editor:
    editor = "nano" if os.name != "nt" else "notepad"
  fd, tmp_path = tempfile.mkstemp(prefix="json_leaf_", suffix=".txt", text=True)
  try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
      f.write(initial_text)
    try:
      proc = subprocess.run([editor, tmp_path])
      if proc.returncode != 0:
        return None
    except FileNotFoundError:
      return None
    with open(tmp_path, "r", encoding="utf-8") as f:
      return f.read()
  finally:
    try:
      os.remove(tmp_path)
    except Exception:
      pass


# ---------- Small modal-like helper apps ----------

class ValueViewer(ModalScreen[None]):
  """Minimal modal-like screen for showing text content."""
  CSS = """
  Screen { align: center middle; }
  .modal {
    width: 90%;
    height: 80%;
    border: round $accent;
    padding: 1 2;
    background: $panel;
  }
  .title { padding: 0 1; text-style: bold; }
  .viewer { height: 1fr; margin-top: 1; border: round $surface; }
  .buttons { height: auto; padding-top: 1; }
  .ml2 { margin-left: 2; }
  """

  def __init__(self, title: str, content: str) -> None:
    super().__init__()
    self._title = title
    self._content = content

  def compose(self) -> ComposeResult:
    yield Container(
      Label(self._title, classes="title"),
      _LogWidget(classes="viewer"),
      Horizontal(
        Button("Close (Esc)", id="close", variant="primary"),
        classes="buttons",
      ),
      classes="modal",
    )

  def on_mount(self) -> None:
    log = self.query_one(_LogWidget)
    _log_write_lines(log, self._content)
    self.set_focus(log)

  def on_button_pressed(self, event: Button.Pressed) -> None:
    if event.button.id == "close":
      self.dismiss(None)

  BINDINGS = [Binding("escape", "close", "Close")]

  def action_close(self) -> None:
    self.dismiss(None)


@dataclass
class Base64Result:
  decoded_text: str | None
  decoded_bytes_preview: str | None
  replacement_value: str | None


class Base64DecodeScreen(ModalScreen[Base64Result | None]):
  """Modal-like screen to preview Base64 decode and optionally replace leaf."""
  CSS = ValueViewer.CSS

  def __init__(self, title: str, src_value: str) -> None:
    super().__init__()
    self._title = title
    self._src = src_value
    self._result: Base64Result | None = None

  def compose(self) -> ComposeResult:
    yield Container(
      Label(self._title, classes="title"),
      _LogWidget(classes="viewer"),
      Horizontal(
        Button("Replace leaf with decoded", id="replace", variant="success"),
        Button("Close (Esc)", id="close", variant="primary", classes="ml2"),
        classes="buttons",
      ),
      classes="modal",
    )

  def on_mount(self) -> None:
    log = self.query_one(_LogWidget)
    try:
      raw = base64.b64decode(self._src, validate=True)
      try:
        text = raw.decode("utf-8")
        preview = None
        repl = text
        _log_write_lines(log, "✅ Base64 decoded as UTF-8 text:\n" + text)
      except UnicodeDecodeError:
        text = None
        preview = hexdump(raw)
        repl = raw.decode("latin-1", errors="ignore")
        _log_write_lines(log, "✅ Base64 decoded as bytes (hex):\n" + preview)
      self._result = Base64Result(text, preview, repl)
    except Exception as e:
      _log_write_lines(log, f"❌ Decode failed: {e!r}")
      self.query_one("#replace", Button).display = False

  def on_button_pressed(self, event: Button.Pressed) -> None:
    if event.button.id == "replace":
      self.dismiss(self._result if self._result else None)
    elif event.button.id == "close":
      self.dismiss(None)

  BINDINGS = [Binding("escape", "close", "Close")]

  def action_close(self) -> None:
    self.dismiss(None)


class OpsMenuScreen(ModalScreen[str | None]):
  """Operations menu for a leaf: dismisses with 'display' | 'b64' | 'edit' | None."""
  CSS = """
  Screen { align: center middle; }
  .modal { width: 60%; border: round $accent; padding: 1 2; background: $panel; }
  .title { padding: 0 1; text-style: bold; }
  """

  def __init__(self, for_path: Path) -> None:
    super().__init__()
    self._path = for_path

  def compose(self) -> ComposeResult:
    opts = OptionList(
      Option("Display", id="display"),
      Option("Base64 decode", id="b64"),
      Option("Edit (in $EDITOR)", id="edit"),
      Option("Cancel", id="cancel"),
    )
    yield Container(
      Label(f"Operations for {path_to_str(self._path)}", classes="title"),
      opts,
      classes="modal",
    )

  def on_mount(self) -> None:
    self.set_focus(self.query_one(OptionList))

  def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
    opt = event.option.id or ""
    self.dismiss(None if opt == "cancel" else opt)

  BINDINGS = [Binding("escape", "cancel", "Cancel")]

  def action_cancel(self) -> None:
    self.dismiss(None)


# ---------- Main App ----------

@dataclass
class NodeMeta:
  path: Path
  kind: str        # 'dict' | 'list' | 'leaf'
  loaded: bool     # children populated

class JSONTreeApp(App):
  CSS = """
  Screen { align: center middle; }
  .title { padding: 0 1; text-style: bold; }
  .modal {
    width: 90%;
    height: 80%;
    border: round $accent;
    padding: 1 2;
    background: $panel;
  }
  .viewer { height: 1fr; margin-top: 1; border: round $surface; }
  .buttons { height: auto; padding-top: 1; }
  .ml2 { margin-left: 2; }
  #body { width: 100%; height: 100%; padding: 0 1; }
  """

  BINDINGS = [
    Binding("q", "quit", "Quit"),
    Binding("e", "edit_selected", "Edit leaf"),
    Binding("o", "ops_selected", "Leaf ops"),
    Binding("d", "display_selected", "Display leaf"),
  ]

  def __init__(self, data: JSONType, root_label: str = "JSON") -> None:
    super().__init__()
    self.data: JSONType = data
    self.root_label = root_label

  def compose(self) -> ComposeResult:
    yield Header()
    with Container(id="body"):
      yield Tree(self.root_label, id="tree")
    yield Footer()

  def on_mount(self) -> None:
    tree = self.query_one(Tree)
    tree.show_root = True
    root_meta = NodeMeta((), "dict" if isinstance(self.data, dict) else "list" if isinstance(self.data, list) else "leaf", False)
    tree.root.data = root_meta
    tree.root.allow_expand = root_meta.kind in ("dict", "list")
    tree.root.collapse()
    self.set_focus(tree)

  # --- lazy children population ---
  def _populate_children(self, node: Tree.Node) -> None:
    meta: NodeMeta = node.data
    value = get_by_path(self.data, meta.path) if meta.path else self.data
    node.remove_children()
    if isinstance(value, dict):
      for k in sorted(value.keys(), key=str):
        v = value[k]
        child_path = (*meta.path, k)
        if is_leaf(v):
          label = f"{k}: (...)"
          child = node.add(label, data=NodeMeta(child_path, "leaf", True))
          child.allow_expand = False
        else:
          label = f"{k}:"
          child = node.add(label, data=NodeMeta(child_path, "dict" if isinstance(v, dict) else "list", False))
          child.allow_expand = True
    elif isinstance(value, list):
      for i, v in enumerate(value):
        child_path = (*meta.path, i)
        if is_leaf(v):
          label = f"[{i}]: (...)"
          child = node.add(label, data=NodeMeta(child_path, "leaf", True))
          child.allow_expand = False
        else:
          label = f"[{i}]:"
          child = node.add(label, data=NodeMeta(child_path, "dict" if isinstance(v, dict) else "list", False))
          child.allow_expand = True
    meta.loaded = True

  # --- events ---
  def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
    node = event.node
    meta: NodeMeta = node.data
    if meta.kind in ("dict", "list") and not meta.loaded:
      self._populate_children(node)

  def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
    node = event.node
    meta: NodeMeta = node.data
    if meta.kind == "leaf":
      self.call_after_refresh(self._open_ops_for_node, node)
      event.stop()
    else:
      node.toggle()

  # --- actions ---
  def _value_as_text(self, node: Tree.Node) -> str:
    meta: NodeMeta = node.data
    value = get_by_path(self.data, meta.path)
    return pretty_repr(value)

  def _open_ops_for_node(self, node: Tree.Node) -> None:
    meta: NodeMeta = node.data
    screen = OpsMenuScreen(meta.path)

    def handle_choice(choice: str | None) -> None:
      if choice == "display":
        self._display_leaf(node)
      elif choice == "b64":
        self._b64_leaf(node)
      elif choice == "edit":
        self._edit_leaf(node)

    self.push_screen(screen, callback=handle_choice)

  def _display_leaf(self, node: Tree.Node) -> None:
    meta: NodeMeta = node.data
    val_text = self._value_as_text(node)
    self.push_screen(ValueViewer(f"Display {path_to_str(meta.path)}", val_text))

  def _b64_leaf(self, node: Tree.Node) -> None:
    meta: NodeMeta = node.data
    val = get_by_path(self.data, meta.path)
    if not isinstance(val, str):
      self.push_screen(ValueViewer("Base64 decode", "Leaf value is not a string."))
      return
    screen = Base64DecodeScreen(f"Base64 decode of {path_to_str(meta.path)}", val)

    def handle_base64(result: Base64Result | None) -> None:
      if result and result.replacement_value is not None:
        replacement: Any = result.replacement_value
        if result.decoded_text is not None:
          text = result.decoded_text
          stripped = text.lstrip()
          if stripped.startswith("{") or stripped.startswith("["):
            try:
              parsed = json.loads(text)
            except json.JSONDecodeError:
              parsed = None
            else:
              replacement = parsed
        try:
          set_by_path(self.data, meta.path, replacement)
        except Exception as e:
          self.push_screen(ValueViewer("Error", f"Failed to replace value: {e!r}"))
          return
        self._refresh_tree_after_value_change(meta.path)

    self.push_screen(screen, callback=handle_base64)

  def _find_node_by_path(self, path: Path) -> Tree.Node | None:
    tree = self.query_one(Tree)
    stack: List[Tree.Node] = [tree.root]
    while stack:
      node = stack.pop()
      node_meta: NodeMeta = node.data
      if node_meta.path == path:
        return node
      stack.extend(node.children)
    return None

  def _refresh_tree_after_value_change(self, path: Path) -> None:
    new_value = get_by_path(self.data, path) if path else self.data
    is_branch = isinstance(new_value, (dict, list))
    if not path:
      tree = self.query_one(Tree)
      node = tree.root
      meta: NodeMeta = node.data
      if isinstance(new_value, dict):
        meta.kind = "dict"
      elif isinstance(new_value, list):
        meta.kind = "list"
      else:
        meta.kind = "leaf"
      node.allow_expand = meta.kind in ("dict", "list")
      node.remove_children()
      if meta.kind in ("dict", "list"):
        meta.loaded = False
        self._populate_children(node)
        if is_branch:
          node.expand()
      else:
        meta.loaded = True
      return

    parent_path = path[:-1]
    parent_node = self._find_node_by_path(parent_path)
    if parent_node is None:
      return
    parent_meta: NodeMeta = parent_node.data
    if parent_meta.kind not in ("dict", "list"):
      return
    parent_meta.loaded = False
    self._populate_children(parent_node)
    if is_branch:
      parent_node.expand()
      new_node = self._find_node_by_path(path)
      if new_node is not None:
        new_meta: NodeMeta = new_node.data
        new_meta.loaded = False
        self._populate_children(new_node)
        new_node.expand()

  def _edit_leaf(self, node: Tree.Node) -> None:
    meta: NodeMeta = node.data
    old = get_by_path(self.data, meta.path)
    initial = old if isinstance(old, str) else json.dumps(old, indent=2, ensure_ascii=False)
    edited = open_in_editor(initial)
    if edited is None:
      return
    if isinstance(old, str):
      new_value: Any = edited
    else:
      try:
        new_value = json.loads(edited)
      except json.JSONDecodeError:
        new_value = edited
    try:
      set_by_path(self.data, meta.path, new_value)
    except Exception as e:
      self.push_screen(ValueViewer("Error", f"Failed to set value: {e!r}"))

  # shortcuts
  def action_edit_selected(self) -> None:
    tree = self.query_one(Tree)
    node = tree.cursor_node or tree.root
    meta: NodeMeta = node.data
    if meta.kind == "leaf":
      self._edit_leaf(node)

  def action_display_selected(self) -> None:
    tree = self.query_one(Tree)
    node = tree.cursor_node or tree.root
    meta: NodeMeta = node.data
    if meta.kind == "leaf":
      self._display_leaf(node)

  def action_ops_selected(self) -> None:
    tree = self.query_one(Tree)
    node = tree.cursor_node or tree.root
    meta: NodeMeta = node.data
    if meta.kind == "leaf":
      self._open_ops_for_node(node)


# ---------- CLI ----------

def main() -> None:
  parser = argparse.ArgumentParser(
    description="Interactive JSON explorer/editor (Textual). Shows key tree with '(...)' leaves."
  )
  parser.add_argument("--in", dest="inpath", help="Path to JSON file. If omitted, reads JSON from stdin.")
  parser.add_argument("--title", default="JSON", help="Root label/title for the tree.")
  args = parser.parse_args()

  data = read_json_from_args_or_stdin(args.inpath)
  app = JSONTreeApp(data, root_label=args.title)
  app.run()

if __name__ == "__main__":
  main()
