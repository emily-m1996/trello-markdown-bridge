# kanbanbridge

Converts kanban board exports between Trello's JSON export format and a plain
Markdown kanban format. I wanted to move a couple of boards out of Trello and
into a Markdown file I could keep in a notes vault and diff in git, and back
again when a collaborator wanted to re-import into Trello.

No third-party dependencies. Standard library only.

## Install

```
pip install -e .
```

This gives you a `kanbanbridge` command. You can also run it without
installing via `python -m kanbanbridge.cli`.

## Usage

```
kanbanbridge board.json board.md
kanbanbridge board.md board.json
```

The format is guessed from the file extension (`.json` -> Trello,
`.md`/`.markdown` -> Markdown). Override it explicitly if you're using
different extensions:

```
kanbanbridge export.txt out.txt --from trello --to markdown
```

## Strict by default

By default, conversion fails loudly on anything that would lose or guess at
data: a card referencing a list that doesn't exist, an archived card or list,
an unparseable due date, a markdown file missing its `# Board Name` heading,
and so on. This is meant to catch a bad export or a hand-edited markdown file
before it silently produces a wrong board.

Pass `--lenient` to convert anyway. In lenient mode:

- missing board/list/card names fall back to a placeholder instead of erroring
- archived (`closed`) lists and cards are skipped
- cards pointing at an unknown list id are moved into an "Unsorted" list
- unparseable due dates are dropped instead of raising
- unrecognized lines in a markdown file are ignored

```
kanbanbridge messy-export.json board.md --lenient
```

## The Markdown format

```
# Board Name

## List Name

- [ ] Card title
  > Optional description, can span
  > multiple lines like this.
  - [ ] A checklist sub-task
  - [x] A finished checklist sub-task
  - due: 2026-01-15
  - labels: bug, urgent

- [x] A finished card
```

- One `#` heading for the board title.
- One `##` heading per list, in order.
- Each card is a `- [ ]` (open) or `- [x] ` (done) line.
- Indented `> ` lines under a card are appended to its description.
- Indented `- [ ]`/`- [x]` lines under a card are checklist sub-tasks. Trello
  lets a card have several separately named checklists; those are flattened
  into one ordered sub-task list on import, since the markdown format doesn't
  represent checklist names.
- An indented `- due: YYYY-MM-DD` line sets the due date.
- An indented `- labels: a, b, c` line sets a comma-separated label list.

## Trello export format

This reads the same JSON you get from Trello's "Export as JSON" board menu
option: a top-level object with `name`, `lists` (each with `id`, `name`,
`closed`), `cards` (each with `name`, `desc`, `idList`, `closed`, an
optional `due`, an optional `dueComplete` boolean, and an optional `labels`
array), and a top-level `checklists` array (each with `idCard`, `name`, and
`checkItems`, where each check item has a `name` and a `state` of
`"complete"` or `"incomplete"`). `dueComplete` is what a markdown `- [x]`
card round-trips to and from, since Trello has no other board-level "done"
flag outside checklists. Writing back out produces a
minimal version of that same shape — enough for Trello to accept it as an
import, though it doesn't attempt to reproduce every field Trello itself
writes (board backgrounds, member assignments, activity, and so on aren't
modeled here).

## What's not handled yet

Attachments, comments, and Trello label colors are all dropped during
conversion rather than represented in the Markdown format. That's a
deliberate scope cut for now, not a bug.

## License

MIT, see LICENSE.
