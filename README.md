# JSON Navigator (Textual)

A fast, mouse‑friendly terminal **JSON explorer/editor** built with **Textual** and **Rich**. It renders a **collapsed key tree** where leaf values are hidden as `(...)`. Use arrows or the mouse to navigate; **Enter** toggles branches or opens an operations menu for leaves: **Display**, **Base64 decode**, or **Edit** (in your `$EDITOR`).

> ✅ Works across multiple Textual releases (shimmed for `Log`/`TextLog`/`RichLog`, conservative CSS, and portable Tree APIs).

---

## Features

* **Collapsed JSON key tree** with `(...)` for leaf values (keeps secrets and long blobs out of list view).
* **Keyboard & mouse** navigation in the terminal.
* **Enter** on a branch toggles expand/collapse; **Enter** on a leaf opens ops menu.
* **Leaf operations**

  * **Display**: pretty‑prints the full value.
  * **Base64 decode**: previews UTF‑8 text or a hex dump of bytes; optionally replace the leaf value with the decoded content.
  * **Edit**: opens the value in `$EDITOR`; upon save, updates in‑memory JSON.
* **Version‑tolerant UI**: handles differences between Textual versions (tree args, log widget name, CSS properties).
* **No accidental data exposure** in tree labels — only keys + `(...)` are shown.

> Note: Some Textual themes show chevrons/triangles for expand/collapse instead of explicit `+`/`−`. Behavior is the same.

---

## Install

```bash
pip install textual rich
```

Python 3.11–3.13 recommended.

---

## Usage

```bash
# From a file
python json_navigator.py --in path/to/data.json

# From stdin
cat data.json | python json_navigator.py

# Optional: set a custom title for the root
python json_navigator.py --in path/to/data.json --title "My JSON"
```

### Environment

* **$EDITOR** or **$VISUAL** controls which editor opens for **Edit**.

  * Fallbacks: `nano` (POSIX) or `notepad` (Windows).

---

## Keybindings & Controls

| Action                 | Keys/Mouse                                |
| ---------------------- | ----------------------------------------- |
| Move selection         | ↑ ↓ (and mouse)                           |
| Expand/Collapse branch | **Enter** (or mouse double‑click)         |
| Open ops menu on leaf  | **Enter**                                 |
| Display selected leaf  | **d**                                     |
| Base64 decode leaf     | **o** (open ops) → choose *Base64 decode* |
| Edit selected leaf     | **e**                                     |
| Quit                   | **q**                                     |

---

## Operations Details

### Display

Pretty‑prints the selected value using `rich.pretty`. Containers (dict/list) and primitives render clearly.

### Base64 decode

* Attempts `base64.b64decode(..., validate=True)`.
* If result is valid **UTF‑8**, shows decoded text.
* Otherwise, shows a **hex dump** preview of bytes.
* You can **Replace** the leaf with the decoded content (UTF‑8 text, or a Latin‑1 best‑effort string for bytes).

### Edit (in $EDITOR)

* **Strings**: you edit the raw string; result is stored **as a string**.
* **Non‑strings**: initial buffer contains pretty‑printed JSON. On save, the app tries `json.loads(...)`; if parsing fails, it stores the raw edited text **as a string**.

> All edits are in **working memory** only. See *Persisting Changes* below.

---

## Persisting Changes (planned)

Currently the tool edits **in‑memory** only. Planned enhancements:

* `--out FILE` to write the modified JSON on exit.
* `:w` style shortcut to save.
* Confirm‑overwrite prompts.

---

## Compatibility Notes

This project aims to run on a wide range of Textual versions:

* **Log widget**: supports `Log`, `TextLog`, or `RichLog` via a shim.
* **Tree API**: avoids `show_root`/`expand` ctor args; sets properties in `on_mount()` instead.
* **CSS**: uses `text-style: bold;` and avoids unsupported features like `gap:` or adjacent sibling selectors.

If you see an error, try: `python -c "import textual; print(textual.__version__)"` and open an issue.

---

## Troubleshooting

* **`ImportError: cannot import name 'TextLog'`**

  * Fixed by the shim; no action required. If you still see it, upgrade Textual or confirm the file is current.

* **CSS parsing errors (`bold`, `gap`, or `Button + Button`)**

  * The stylesheet uses conservative rules. If your local copy differs, switch to `text-style: bold;`, avoid `gap:`, and prefer simple classes (e.g., `.ml2`).

* **`Tree.__init__() got an unexpected keyword argument 'show_root'`**

  * Use the included version which sets `tree.show_root = True` inside `on_mount()` when available.

* **Editor doesn’t open**

  * Set `$EDITOR` (e.g., `export EDITOR=vim`) or rely on fallback (`nano`/`notepad`).

---

## Roadmap

* Save to file (`--out`, `:w`).
* **Search**: fuzzy key search and **JSONPath** queries (`jsonpath-ng`).
* **Copy value/path** to clipboard (optional `pyperclip`).
* **Add/Delete/Rename** keys and list items.
* **Type coercions** and validators.
* **Diff viewer** (before/after; pretty unified diff for edited leaves).
* **Huge JSON** quality‑of‑life: streaming views, node count limits, and on‑demand loading for massive arrays.

---

## Alternatives / Related Libraries

* **prompt_toolkit** – lower‑level TUI primitives, flexible keymaps.
* **urwid**, **npyscreen** – mature non‑async TUI stacks.
* **orjson**/**ujson** – faster JSON parse/serialize.
* **jsonpath‑ng** – structured querying (future search feature).
* **python‑editor** or `click.edit` – robust editor launching helpers.

Textual alone is sufficient for the core UX; the above can enhance performance or features.

---

## Development

* Style: Python, two‑space indents.
* Single‑file entry point: `json_navigator.py`.
* Keep UI portability in mind: prefer runtime feature checks over hard dependencies on the newest Textual API.

### Run locally

```bash
python json_navigator.py --in examples/sample.json
```

### Linting & type hints (optional)

```bash
pip install ruff mypy
ruff check .
mypy .
```

---

## License

MIT © You. Replace with your preferred license if needed.

---

## Acknowledgements

* Built sing **[Textual](https://github.com/Textualize/textual)** and **[Rich](https://github.com/Textualize/rich)**.

---

## Screenshot / Demo (optional)

> Consider adding a GIF or screenshot in `docs/` and referencing it here once you have one.



