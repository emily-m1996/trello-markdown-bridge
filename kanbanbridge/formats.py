import datetime

from .model import Board, BoardList, Card, ChecklistItem, ConversionError, Label

# Trello's fixed set of label colors, as used in its JSON export. A label with
# no color set has color: null in the export.
TRELLO_LABEL_COLORS = {
    "yellow", "purple", "blue", "red", "green", "orange", "black", "sky", "pink", "lime",
}


def read_trello(data, lenient=False):
    if not isinstance(data, dict):
        raise ConversionError("top-level Trello export must be a JSON object")

    board_name = data.get("name")
    if not board_name:
        if lenient:
            board_name = "Untitled Board"
        else:
            raise ConversionError("board is missing a 'name' field")

    raw_lists = data.get("lists")
    if raw_lists is None:
        if lenient:
            raw_lists = []
        else:
            raise ConversionError("board is missing a 'lists' field")

    lists_by_id = {}
    board_lists = []
    for raw_list in raw_lists:
        list_id = raw_list.get("id")
        list_name = raw_list.get("name")
        if not list_id or not list_name:
            if lenient:
                continue
            raise ConversionError(f"list entry is missing 'id' or 'name': {raw_list!r}")
        if raw_list.get("closed"):
            if lenient:
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
        else:
            raise ConversionError("board is missing a 'cards' field")

    cards_by_id = {}
    unsorted = None
    for raw_card in raw_cards:
        title = raw_card.get("name")
        if not title:
            if lenient:
                continue
            raise ConversionError(f"card entry is missing a 'name': {raw_card!r}")
        if raw_card.get("closed"):
            if lenient:
                continue
            raise ConversionError(f"card '{title}' is archived (closed); rerun with --lenient to skip it")

        due = raw_card.get("due")
        if due:
            due = _parse_trello_date(due, title, lenient)

        labels = []
        for label in raw_card.get("labels") or []:
            label_name = label.get("name")
            if not label_name:
                continue
            label_color = label.get("color")
            if label_color is not None and label_color not in TRELLO_LABEL_COLORS:
                if lenient:
                    label_color = None
                else:
                    raise ConversionError(
                        f"label '{label_name}' on card '{title}' has an unrecognized color {label_color!r}"
                    )
            labels.append(Label(name=label_name, color=label_color))

        card = Card(
            title=title,
            description=raw_card.get("desc", "") or "",
            done=bool(raw_card.get("dueComplete", False)),
            due=due,
            labels=labels,
        )

        target = lists_by_id.get(raw_card.get("idList"))
        if target is None:
            if not lenient:
                raise ConversionError(f"card '{title}' references unknown list id {raw_card.get('idList')!r}")
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
                continue
            raise ConversionError(f"checklist references unknown card id {raw_checklist.get('idCard')!r}")
        for raw_item in raw_checklist.get("checkItems") or []:
            item_name = raw_item.get("name")
            if not item_name:
                if lenient:
                    continue
                raise ConversionError(f"a checklist item on card '{card.title}' is missing a 'name'")
            state = raw_item.get("state")
            if state not in ("complete", "incomplete"):
                if lenient:
                    state = "incomplete"
                else:
                    raise ConversionError(
                        f"checklist item '{item_name}' on card '{card.title}' has an unrecognized state {state!r}"
                    )
            card.checklist_items.append(ChecklistItem(text=item_name, done=state == "complete"))

    return Board(name=board_name, lists=board_lists)


def _parse_trello_date(value, card_title, lenient):
    # Trello timestamps look like "2026-01-15T00:00:00.000Z"; we keep just the date part.
    date_part = value.split("T", 1)[0]
    try:
        datetime.date.fromisoformat(date_part)
    except ValueError:
        if lenient:
            return None
        raise ConversionError(f"card '{card_title}' has an unparseable due date: {value!r}")
    return date_part


def write_trello(board):
    lists = []
    cards = []
    checklists = []
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
            cards.append(entry)
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
    return {"name": board.name, "lists": lists, "cards": cards, "checklists": checklists}


def read_markdown(text, lenient=False):
    board_name = None
    board_lists = []
    current_list = None
    current_card = None

    def require_list():
        nonlocal current_list
        if current_list is None:
            if not lenient:
                raise ConversionError("card appears before any '## List' heading")
            current_list = BoardList(name="Unsorted")
            board_lists.append(current_list)
        return current_list

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        if line.startswith("# "):
            if board_name is not None and not lenient:
                raise ConversionError("found a second top-level '# ' heading; a board can only have one title")
            board_name = line[2:].strip()
            continue

        if line.startswith("## "):
            current_list = BoardList(name=line[3:].strip())
            board_lists.append(current_list)
            current_card = None
            continue

        if line.startswith("- [ ] ") or line.startswith("- [x] "):
            title = line[6:].strip()
            if not title:
                if lenient:
                    continue
                raise ConversionError(f"card checkbox has no title: {raw_line!r}")
            current_card = Card(title=title, done=line.startswith("- [x] "))
            require_list().cards.append(current_card)
            continue

        stripped = line.strip()
        indented = line[:1].isspace()

        if indented and (stripped.startswith("- [ ] ") or stripped.startswith("- [x] ")):
            if current_card is None:
                if lenient:
                    continue
                raise ConversionError(f"checklist item has no preceding card: {raw_line!r}")
            item_text = stripped[6:].strip()
            if not item_text:
                if lenient:
                    continue
                raise ConversionError(f"checklist item has no text: {raw_line!r}")
            current_card.checklist_items.append(
                ChecklistItem(text=item_text, done=stripped.startswith("- [x] "))
            )
            continue

        if stripped.startswith("> "):
            if current_card is None:
                if lenient:
                    continue
                raise ConversionError(f"description line has no preceding card: {raw_line!r}")
            piece = stripped[2:]
            current_card.description = f"{current_card.description}\n{piece}" if current_card.description else piece
            continue

        if stripped.startswith("- due: "):
            if current_card is None:
                if lenient:
                    continue
                raise ConversionError(f"due date line has no preceding card: {raw_line!r}")
            value = stripped[len("- due: "):].strip()
            try:
                datetime.date.fromisoformat(value)
            except ValueError:
                if lenient:
                    continue
                raise ConversionError(f"card '{current_card.title}' has an unparseable due date: {value!r}")
            current_card.due = value
            continue

        if stripped.startswith("- labels: "):
            if current_card is None:
                if lenient:
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
                else:
                    labels.append(Label(name=token))
            current_card.labels = labels
            continue

        if lenient:
            continue
        raise ConversionError(f"unrecognized line: {raw_line!r}")

    if board_name is None:
        if lenient:
            board_name = "Untitled Board"
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
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
