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
- attachments missing a url, and comments missing text, an author, or with an
  unparseable timestamp, are dropped instead of raising
- comments referencing an unknown or deleted card are skipped
- unrecognized lines in a markdown file are ignored

```
kanbanbridge messy-export.json board.md --lenient
```

## Checking an export before converting it

`--dry-run` parses the input, runs the full conversion in memory, and prints a
summary instead of writing the output file. Combine it with `--lenient` to see
exactly what a messy export would cost you before committing to it:

```
$ kanbanbridge messy-export.json board.md --dry-run --lenient
kanbanbridge: dry run OK (trello -> markdown), nothing written
  board: 'Launch Plan'
  3 list(s), 12 card(s)
  2 warning(s):
    - skipped archived card 'Old task'
    - card 'Orphan card' referenced unknown list id 'old-list-id'; moved to 'Unsorted'
```

Without `--lenient`, `--dry-run` just confirms the conversion would succeed
as-is: strict mode raises on the same problems it always does, so there's
nothing to summarize.

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
  - labels: bug:red, urgent
  - attachment: [Design doc](https://example.com/design.pdf)
  - comment: Alex Rivera @ 2026-02-11T09:30:00.000Z
    >> Draft looks good.

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
- An indented `- labels: a, b, c` line sets a comma-separated label list. A
  label carrying one of Trello's fixed colors is written as `name:color`
  (e.g. `bug:red`); a colorless label is just `name`.
- An indented `- attachment: URL` line adds an attachment. If the attachment
  was given a name other than its url in Trello, it's written as
  `- attachment: [name](url)` instead.
- An indented `- comment: AUTHOR @ TIMESTAMP` line starts a comment (the
  `@ TIMESTAMP` part is optional). Its body is one or more `>> ` lines
  indented under it:

  ```
  - comment: Alex Rivera @ 2026-02-11T09:30:00.000Z
    >> Draft looks good.
    >> Ship it.
  ```

## Trello export format

This reads the same JSON you get from Trello's "Export as JSON" board menu
option: a top-level object with `name`, `lists` (each with `id`, `name`,
`closed`), `cards` (each with `name`, `desc`, `idList`, `closed`, an
optional `due`, an optional `dueComplete` boolean, an optional `labels`
array of `{name, color}` objects, where `color` is one of Trello's fixed
label colors or `null`, and an optional `attachments` array of `{name, url}`
objects), a top-level `checklists` array (each with `idCard`, `name`, and
`checkItems`, where each check item has a `name` and a `state` of
`"complete"` or `"incomplete"`), and a top-level `actions` array holding,
among other activity we ignore, comments: entries with `type: "commentCard"`,
a `date`, `data.text`, `data.card.id`, and `memberCreator.fullName` (or
`.username` if the full name isn't set). `dueComplete` is what a markdown
`- [x]` card round-trips to and from, since Trello has no other board-level
"done" flag outside checklists. Writing back out produces a minimal version
of that same shape — enough for Trello to accept it as an import, though it
doesn't attempt to reproduce every field Trello itself writes (board
backgrounds, member assignments, non-comment activity, and so on aren't
modeled here).

## License

MIT, see LICENSE.
