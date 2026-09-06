import datetime

from .model import Attachment, Board, BoardList, Card, ChecklistItem, Comment, ConversionError, Label

# Trello's fixed set of label colors, as used in its JSON export. A label with
# no color set has color: null in the export.
TRELLO_LABEL_COLORS = {
    "yellow", "purple", "blue", "red", "green", "orange", "black", "sky", "pink", "lime",
}


def read_trello(data, lenient=False, diagnostics=None):
    if not isinstance(data, dict):
        raise ConversionError("top-level Trello export must be a JSON object")

    board_name = data.get("name")
    if not board_name:
        if lenient:
            board_name = "Untitled Board"
            _warn(diagnostics, "board is missing a 'name' field; using 'Untitled Board'")
        else:
            raise ConversionError("board is missing a 'name' field")

    raw_lists = data.get("lists")
    if raw_lists is None:
        if lenient:
            raw_lists = []
            _warn(diagnostics, "board is missing a 'lists' field; treating it as empty")
        else:
            raise ConversionError("board is missing a 'lists' field")

    lists_by_id = {}
    board_lists = []
    for raw_list in raw_lists:
        list_id = raw_list.get("id")
        list_name = raw_list.get("name")
        if not list_id or not list_name:
            if lenient:
                _warn(diagnostics, f"skipped list entry missing 'id' or 'name': {raw_list!r}")
                continue
            raise ConversionError(f"list entry is missing 'id' or 'name': {raw_list!r}")
        if raw_list.get("closed"):
            if lenient:
                _warn(diagnostics, f"skipped archived list '{list_name}'")
                continue
            # archiving is a deliberate action in Trello; dropping it silently would lose data
            raise ConversionError(f"list '{list_name}' is archived (closed); rerun with --lenient to skip it")
        board_list = BoardList(name=list_name)
        lists_by_id[list_id] = board_list
        board_lists.append(board_list)

    raw_cards = data.get("cards")
    if raw_cards is None:
        if lenient:
            raw_cards = []
            _warn(diagnostics, "board is missing a 'cards' field; treating it as empty")
        else:
            raise ConversionError("board is missing a 'cards' field")

    cards_by_id = {}
    unsorted = None
    for raw_card in raw_cards:
        title = raw_card.get("name")
        if not title:
            if lenient:
                _warn(diagnostics, f"skipped card entry missing a 'name': {raw_card!r}")
                continue
            raise ConversionError(f"card entry is missing a 'name': {raw_card!r}")
        if raw_card.get("closed"):
            if lenient:
                _warn(diagnostics, f"skipped archived card '{title}'")
                continue
            raise ConversionError(f"card '{title}' is archived (closed); rerun with --lenient to skip it")

        due = raw_card.get("due")
        if due:
            due = _parse_trello_date(due, title, lenient, diagnostics)

        labels = []
        for label in raw_card.get("labels") or []:
            label_name = label.get("name")
            if not label_name:
                continue
            label_color = label.get("color")
            if label_color is not None and label_color not in TRELLO_LABEL_COLORS:
                if lenient:
                    _warn(
                        diagnostics,
                        f"label '{label_name}' on card '{title}' had unrecognized color "
                        f"{label_color!r}; treating it as colorless",
                    )
                    label_color = None
                else:
                    raise ConversionError(
                        f"label '{label_name}' on card '{title}' has an unrecognized color {label_color!r}"
                    )
            labels.append(Label(name=label_name, color=label_color))

        attachments = []
        for raw_attachment in raw_card.get("attachments") or []:
            url = raw_attachment.get("url")
            if not url:
                if lenient:
                    _warn(diagnostics, f"skipped an attachment with no url on card '{title}'")
                    continue
                raise ConversionError(f"an attachment on card '{title}' is missing a 'url'")
            name = raw_attachment.get("name")
            if name == url:
                name = None
            attachments.append(Attachment(url=url, name=name))

        card = Card(
            title=title,
            description=raw_card.get("desc", "") or "",
            done=bool(raw_card.get("dueComplete", False)),
            due=due,
            labels=labels,
            attachments=attachments,
        )

        target = lists_by_id.get(raw_card.get("idList"))
        if target is None:
            if not lenient:
                raise ConversionError(f"card '{title}' references unknown list id {raw_card.get('idList')!r}")
            _warn(
                diagnostics,
                f"card '{title}' referenced unknown list id {raw_card.get('idList')!r}; moved to 'Unsorted'",
            )
            if unsorted is None:
                unsorted = BoardList(name="Unsorted")
                board_lists.append(unsorted)
            target = unsorted
        target.cards.append(card)
        raw_id = raw_card.get("id")
        if raw_id:
            cards_by_id[raw_id] = card

    for raw_checklist in data.get("checklists") or []:
        card = cards_by_id.get(raw_checklist.get("idCard"))
        if card is None:
            if lenient:
                _warn(diagnostics, f"skipped checklist referencing unknown card id {raw_checklist.get('idCard')!r}")
                continue
            raise ConversionError(f"checklist references unknown card id {raw_checklist.get('idCard')!r}")
        for raw_item in raw_checklist.get("checkItems") or []:
            item_name = raw_item.get("name")
            if not item_name:
                if lenient:
                    _warn(diagnostics, f"skipped a checklist item on card '{card.title}' missing a 'name'")
                    continue
                raise ConversionError(f"a checklist item on card '{card.title}' is missing a 'name'")
            state = raw_item.get("state")
            if state not in ("complete", "incomplete"):
                if lenient:
                    _warn(
                        diagnostics,
                        f"checklist item '{item_name}' on card '{card.title}' had unrecognized state "
                        f"{state!r}; treating it as incomplete",
                    )
                    state = "incomplete"
                else:
                    raise ConversionError(
                        f"checklist item '{item_name}' on card '{card.title}' has an unrecognized state {state!r}"
                    )
            card.checklist_items.append(ChecklistItem(text=item_name, done=state == "complete"))

    for raw_action in data.get("actions") or []:
        if raw_action.get("type") != "commentCard":
            continue
        raw_data = raw_action.get("data") or {}
        card = cards_by_id.get((raw_data.get("card") or {}).get("id"))
        if card is None:
            if lenient:
                _warn(diagnostics, "skipped a comment referencing an unknown or deleted card")
                continue
            raise ConversionError("a comment action references an unknown or deleted card")
        text = raw_data.get("text")
        if not text:
            if lenient:
                _warn(diagnostics, f"skipped an empty comment on card '{card.title}'")
                continue
            raise ConversionError(f"a comment on card '{card.title}' has no text")
        member = raw_action.get("memberCreator") or {}
        author = member.get("fullName") or member.get("username")
        if not author:
            if lenient:
                _warn(diagnostics, f"comment on card '{card.title}' has no author; using 'Unknown'")
                author = "Unknown"
            else:
                raise ConversionError(f"a comment on card '{card.title}' has no author")
        date = raw_action.get("date")
        if date:
            date = _parse_trello_datetime(date, card.title, lenient, diagnostics)
        card.comments.append(Comment(author=author, text=text, date=date))

    return Board(name=board_name, lists=board_lists)


def _warn(diagnostics, message):
    if diagnostics is not None:
        diagnostics.warn(message)


def _parse_trello_date(value, card_title, lenient, diagnostics=None):
    # Trello timestamps look like "2026-01-15T00:00:00.000Z"; we keep just the date part.
    date_part = value.split("T", 1)[0]
    try:
        datetime.date.fromisoformat(date_part)
    except ValueError:
        if lenient:
            _warn(diagnostics, f"dropped unparseable due date on card '{card_title}': {value!r}")
            return None
        raise ConversionError(f"card '{card_title}' has an unparseable due date: {value!r}")
    return date_part


def _parse_trello_datetime(value, card_title, lenient, diagnostics=None):
    # Unlike due dates, comment timestamps keep their time-of-day, so we validate
    # the whole thing but store it as-is rather than truncating to a date.
    try:
        datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        if lenient:
            _warn(diagnostics, f"dropped unparseable comment timestamp on card '{card_title}': {value!r}")
            return None
        raise ConversionError(f"a comment on card '{card_title}' has an unparseable timestamp: {value!r}")
    return value


def write_trello(board):
    lists = []
    cards = []
    checklists = []
    actions = []
    for index, board_list in enumerate(board.lists):
        list_id = f"list{index}"
        lists.append({"id": list_id, "name": board_list.name, "closed": False})
        for card_index, card in enumerate(board_list.cards):
            card_id = f"{list_id}-card{card_index}"
            entry = {
                "id": card_id,
                "name": card.title,
                "desc": card.description,
                "idList": list_id,
                "closed": False,
                "dueComplete": card.done,
            }
            if card.due:
                entry["due"] = f"{card.due}T00:00:00.000Z"
            if card.labels:
                entry["labels"] = [{"name": label.name, "color": label.color} for label in card.labels]
            if card.attachments:
                entry["attachments"] = [
                    {"name": attachment.name or attachment.url, "url": attachment.url}
                    for attachment in card.attachments
                ]
            cards.append(entry)
            for comment_index, comment in enumerate(card.comments):
                action = {
                    "id": f"{card_id}-comment{comment_index}",
                    "type": "commentCard",
                    "data": {"text": comment.text, "card": {"id": card_id}},
                    "memberCreator": {"fullName": comment.author},
                }
                if comment.date:
                    action["date"] = comment.date
                actions.append(action)
            if card.checklist_items:
                checklist_id = f"{card_id}-checklist"
                entry["idChecklists"] = [checklist_id]
                checklists.append(
                    {
                        "id": checklist_id,
                        "idCard": card_id,
                        "name": "Checklist",
                        "checkItems": [
                            {
                                "id": f"{checklist_id}-item{item_index}",
                                "name": item.text,
                                "state": "complete" if item.done else "incomplete",
                            }
                            for item_index, item in enumerate(card.checklist_items)
                        ],
                    }
                )
    return {"name": board.name, "lists": lists, "cards": cards, "checklists": checklists, "actions": actions}


def read_markdown(text, lenient=False, diagnostics=None):
    board_name = None
    board_lists = []
    current_list = None
    current_card = None
    current_comment = None

    def require_list():
        nonlocal current_list
        if current_list is None:
            if not lenient:
                raise ConversionError("card appears before any '## List' heading")
            _warn(diagnostics, "card appeared before any '## List' heading; filed under 'Unsorted'")
            current_list = BoardList(name="Unsorted")
            board_lists.append(current_list)
        return current_list

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        if line.startswith("# "):
            if board_name is not None:
                if not lenient:
                    raise ConversionError("found a second top-level '# ' heading; a board can only have one title")
                _warn(diagnostics, f"found a second top-level heading {line[2:].strip()!r}; kept the last one")
            board_name = line[2:].strip()
            continue

        if line.startswith("## "):
            current_list = BoardList(name=line[3:].strip())
            board_lists.append(current_list)
            current_card = None
            current_comment = None
            continue

        if line.startswith("- [ ] ") or line.startswith("- [x] "):
            title = line[6:].strip()
            if not title:
                if lenient:
                    _warn(diagnostics, f"skipped a card checkbox with no title: {raw_line!r}")
                    continue
                raise ConversionError(f"card checkbox has no title: {raw_line!r}")
            current_card = Card(title=title, done=line.startswith("- [x] "))
            current_comment = None
            require_list().cards.append(current_card)
            continue

        stripped = line.strip()
        indented = line[:1].isspace()

        if indented and (stripped.startswith("- [ ] ") or stripped.startswith("- [x] ")):
            if current_card is None:
                if lenient:
                    _warn(diagnostics, f"skipped a checklist item with no preceding card: {raw_line!r}")
                    continue
                raise ConversionError(f"checklist item has no preceding card: {raw_line!r}")
            item_text = stripped[6:].strip()
            if not item_text:
                if lenient:
                    _warn(diagnostics, f"skipped a checklist item with no text: {raw_line!r}")
                    continue
                raise ConversionError(f"checklist item has no text: {raw_line!r}")
            current_card.checklist_items.append(
                ChecklistItem(text=item_text, done=stripped.startswith("- [x] "))
            )
            continue

        if stripped.startswith(">> "):
            if current_comment is None:
                if lenient:
                    _warn(diagnostics, f"skipped a comment text line with no preceding comment: {raw_line!r}")
                    continue
                raise ConversionError(f"comment text line has no preceding comment: {raw_line!r}")
            piece = stripped[3:]
            current_comment.text = f"{current_comment.text}\n{piece}" if current_comment.text else piece
            continue

        if stripped.startswith("> "):
            if current_card is None:
                if lenient:
                    _warn(diagnostics, f"skipped a description line with no preceding card: {raw_line!r}")
                    continue
                raise ConversionError(f"description line has no preceding card: {raw_line!r}")
            piece = stripped[2:]
            current_card.description = f"{current_card.description}\n{piece}" if current_card.description else piece
            continue

        if stripped.startswith("- due: "):
            if current_card is None:
                if lenient:
                    _warn(diagnostics, f"skipped a due date line with no preceding card: {raw_line!r}")
                    continue
                raise ConversionError(f"due date line has no preceding card: {raw_line!r}")
            value = stripped[len("- due: "):].strip()
            try:
                datetime.date.fromisoformat(value)
            except ValueError:
                if lenient:
                    _warn(diagnostics, f"dropped unparseable due date on card '{current_card.title}': {value!r}")
                    continue
                raise ConversionError(f"card '{current_card.title}' has an unparseable due date: {value!r}")
            current_card.due = value
            continue

        if stripped.startswith("- labels: "):
            if current_card is None:
                if lenient:
                    _warn(diagnostics, f"skipped a labels line with no preceding card: {raw_line!r}")
                    continue
                raise ConversionError(f"labels line has no preceding card: {raw_line!r}")
            value = stripped[len("- labels: "):].strip()
            labels = []
            for token in value.split(","):
                token = token.strip()
                if not token:
                    continue
                name, sep, color = token.rpartition(":")
                if sep and color in TRELLO_LABEL_COLORS:
                    labels.append(Label(name=name.strip(), color=color))
                elif sep and not lenient:
                    raise ConversionError(
                        f"label '{token}' on card '{current_card.title}' has an unrecognized color {color!r}"
                    )
                elif sep:
                    _warn(
                        diagnostics,
                        f"label '{token}' on card '{current_card.title}' had unrecognized color "
                        f"{color!r}; kept the full token as the label name",
                    )
                    labels.append(Label(name=token))
                else:
                    labels.append(Label(name=token))
            current_card.labels = labels
            continue

        if stripped.startswith("- attachment: "):
            if current_card is None:
                if lenient:
                    _warn(diagnostics, f"skipped an attachment line with no preceding card: {raw_line!r}")
                    continue
                raise ConversionError(f"attachment line has no preceding card: {raw_line!r}")
            value = stripped[len("- attachment: "):].strip()
            if value.startswith("[") and "](" in value and value.endswith(")"):
                name, _, rest = value[1:].partition("](")
                url = rest[:-1]
            else:
                name, url = None, value
            if not url:
                if lenient:
                    _warn(diagnostics, f"skipped an attachment with no url on card '{current_card.title}'")
                    continue
                raise ConversionError(f"an attachment on card '{current_card.title}' is missing a url")
            current_card.attachments.append(Attachment(url=url, name=name))
            continue

        if stripped.startswith("- comment: "):
            if current_card is None:
                if lenient:
                    _warn(diagnostics, f"skipped a comment line with no preceding card: {raw_line!r}")
                    continue
                raise ConversionError(f"comment line has no preceding card: {raw_line!r}")
            value = stripped[len("- comment: "):].strip()
            author, sep, date = value.partition(" @ ")
            author = author.strip()
            date = date.strip() if sep else None
            if not author:
                if lenient:
                    _warn(diagnostics, f"skipped a comment with no author on card '{current_card.title}'")
                    continue
                raise ConversionError(f"a comment on card '{current_card.title}' is missing an author")
            current_comment = Comment(author=author, text="", date=date or None)
            current_card.comments.append(current_comment)
            continue

        if lenient:
            _warn(diagnostics, f"ignored unrecognized line: {raw_line!r}")
            continue
        raise ConversionError(f"unrecognized line: {raw_line!r}")

    if board_name is None:
        if lenient:
            board_name = "Untitled Board"
            _warn(diagnostics, "markdown file is missing a top-level '# Board Name' heading; using 'Untitled Board'")
        else:
            raise ConversionError("markdown file is missing a top-level '# Board Name' heading")

    return Board(name=board_name, lists=board_lists)


def write_markdown(board):
    lines = [f"# {board.name}", ""]
    for board_list in board.lists:
        lines.append(f"## {board_list.name}")
        lines.append("")
        for card in board_list.cards:
            marker = "x" if card.done else " "
            lines.append(f"- [{marker}] {card.title}")
            for desc_line in card.description.splitlines():
                lines.append(f"  > {desc_line}")
            for item in card.checklist_items:
                item_marker = "x" if item.done else " "
                lines.append(f"  - [{item_marker}] {item.text}")
            if card.due:
                lines.append(f"  - due: {card.due}")
            if card.labels:
                rendered = [
                    f"{label.name}:{label.color}" if label.color else label.name for label in card.labels
                ]
                lines.append(f"  - labels: {', '.join(rendered)}")
            for attachment in card.attachments:
                value = f"[{attachment.name}]({attachment.url})" if attachment.name else attachment.url
                lines.append(f"  - attachment: {value}")
            for comment in card.comments:
                header = f"{comment.author} @ {comment.date}" if comment.date else comment.author
                lines.append(f"  - comment: {header}")
                for comment_line in comment.text.splitlines():
                    lines.append(f"    >> {comment_line}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
