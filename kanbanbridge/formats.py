import datetime

from .model import Board, BoardList, Card, ConversionError


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
            if label_name:
                labels.append(label_name)

        card = Card(
            title=title,
            description=raw_card.get("desc", "") or "",
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
    for index, board_list in enumerate(board.lists):
        list_id = f"list{index}"
        lists.append({"id": list_id, "name": board_list.name, "closed": False})
        for card_index, card in enumerate(board_list.cards):
            entry = {
                "id": f"{list_id}-card{card_index}",
                "name": card.title,
                "desc": card.description,
                "idList": list_id,
                "closed": False,
            }
            if card.due:
                entry["due"] = f"{card.due}T00:00:00.000Z"
            if card.labels:
                entry["labels"] = [{"name": label, "color": None} for label in card.labels]
            cards.append(entry)
    return {"name": board.name, "lists": lists, "cards": cards}


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
            current_card.labels = [label.strip() for label in value.split(",") if label.strip()]
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
            if card.due:
                lines.append(f"  - due: {card.due}")
            if card.labels:
                lines.append(f"  - labels: {', '.join(card.labels)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
