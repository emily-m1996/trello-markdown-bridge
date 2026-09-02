import unittest

from kanbanbridge.formats import read_markdown, read_trello, write_markdown, write_trello
from kanbanbridge.model import Board, BoardList, Card, ChecklistItem, ConversionError, Label

# Fixture boards meant to stand in for real exports: a couple of lists, cards
# with every field populated, an empty list, and some non-ASCII text to make
# sure nothing is being silently transcoded along the way.
FIXTURE_BOARDS = [
    Board(
        name="Solo Card",
        lists=[BoardList(name="Todo", cards=[Card(title="Just a title")])],
    ),
    Board(
        name="Home Renovation",
        lists=[
            BoardList(
                name="Backlog",
                cards=[
                    Card(
                        title="Get quotes for kitchen tile",
                        description="Call the three places on the fridge list.\nAsk about lead time.",
                        due="2026-03-01",
                        labels=[Label(name="research", color="sky"), Label(name="urgent", color="red")],
                        checklist_items=[
                            ChecklistItem(text="Call Ferguson Tile", done=True),
                            ChecklistItem(text="Call Home Depot"),
                            ChecklistItem(text="Call the place on 5th"),
                        ],
                    ),
                    Card(title="Pick a paint color", done=True),
                ],
            ),
            BoardList(name="Doing", cards=[Card(title="Demo the bathroom", labels=[Label(name="messy")])]),
            BoardList(name="Done", cards=[]),
        ],
    ),
    Board(
        name="Café Menu Ideas — v2",
        lists=[
            BoardList(
                name="Specials",
                cards=[Card(title="Soupe à l'oignon", description="Needs gruyère, not cheddar.")],
            )
        ],
    ),
]


class RoundTripTests(unittest.TestCase):
    def test_trello_round_trip(self):
        for board in FIXTURE_BOARDS:
            with self.subTest(board=board.name):
                restored = read_trello(write_trello(board))
                self.assertEqual(restored, board)

    def test_markdown_round_trip(self):
        for board in FIXTURE_BOARDS:
            with self.subTest(board=board.name):
                restored = read_markdown(write_markdown(board))
                self.assertEqual(restored, board)

    def test_full_cycle_trello_to_markdown_and_back(self):
        for board in FIXTURE_BOARDS:
            with self.subTest(board=board.name):
                via_trello = read_trello(write_trello(board))
                via_markdown = read_markdown(write_markdown(via_trello))
                self.assertEqual(via_markdown, board)


class RawFixtureParsingTests(unittest.TestCase):
    """Parse hand-written exports rather than ones this codebase produced itself,
    so a schema drift between read_trello and write_trello wouldn't hide a bug."""

    def test_parses_a_realistic_trello_export(self):
        raw = {
            "name": "Launch Plan",
            "lists": [
                {"id": "l1", "name": "To Do", "closed": False},
                {"id": "l2", "name": "Archived List", "closed": True},
            ],
            "cards": [
                {
                    "id": "c1",
                    "name": "Write announcement",
                    "desc": "Draft in the shared doc first.",
                    "idList": "l1",
                    "closed": False,
                    "due": "2026-02-10T00:00:00.000Z",
                    "labels": [{"name": "writing", "color": "green"}, {"name": "no color", "color": None}],
                },
                {
                    "id": "c2",
                    "name": "Old task",
                    "desc": "",
                    "idList": "l2",
                    "closed": True,
                },
            ],
            "checklists": [
                {
                    "id": "cl1",
                    "idCard": "c1",
                    "name": "Steps",
                    "checkItems": [
                        {"id": "ci1", "name": "Draft copy", "state": "complete"},
                        {"id": "ci2", "name": "Get sign-off", "state": "incomplete"},
                    ],
                },
                {
                    "id": "cl2",
                    "idCard": "c1",
                    "name": "Distribution",
                    "checkItems": [
                        {"id": "ci3", "name": "Post to blog", "state": "incomplete"},
                    ],
                },
            ],
        }
        board = read_trello(raw, lenient=True)
        self.assertEqual(board.name, "Launch Plan")
        self.assertEqual([lst.name for lst in board.lists], ["To Do"])
        card = board.lists[0].cards[0]
        self.assertEqual(card.title, "Write announcement")
        self.assertEqual(card.description, "Draft in the shared doc first.")
        self.assertEqual(card.due, "2026-02-10")
        self.assertEqual(card.labels, [Label(name="writing", color="green"), Label(name="no color")])
        # both named checklists on the card flatten into one ordered sub-task list
        self.assertEqual(
            card.checklist_items,
            [
                ChecklistItem(text="Draft copy", done=True),
                ChecklistItem(text="Get sign-off", done=False),
                ChecklistItem(text="Post to blog", done=False),
            ],
        )

    def test_parses_the_readme_example(self):
        text = (
            "# Board Name\n"
            "\n"
            "## List Name\n"
            "\n"
            "- [ ] Card title\n"
            "  > Optional description, can span\n"
            "  > multiple lines like this.\n"
            "  - [x] A finished sub-task\n"
            "  - [ ] An open sub-task\n"
            "  - due: 2026-01-15\n"
            "  - labels: bug:red, urgent\n"
            "\n"
            "- [x] A finished card\n"
        )
        board = read_markdown(text)
        self.assertEqual(board.name, "Board Name")
        self.assertEqual(len(board.lists), 1)
        first, second = board.lists[0].cards
        self.assertEqual(first.title, "Card title")
        self.assertFalse(first.done)
        self.assertEqual(first.description, "Optional description, can span\nmultiple lines like this.")
        self.assertEqual(
            first.checklist_items,
            [ChecklistItem(text="A finished sub-task", done=True), ChecklistItem(text="An open sub-task")],
        )
        self.assertEqual(first.due, "2026-01-15")
        self.assertEqual(first.labels, [Label(name="bug", color="red"), Label(name="urgent")])
        self.assertEqual(second.title, "A finished card")
        self.assertTrue(second.done)


class LabelColorTests(unittest.TestCase):
    def test_unrecognized_trello_color_raises_in_strict_mode(self):
        raw = {
            "name": "Board",
            "lists": [{"id": "l1", "name": "To Do", "closed": False}],
            "cards": [
                {
                    "id": "c1",
                    "name": "Card",
                    "idList": "l1",
                    "labels": [{"name": "weird", "color": "mauve"}],
                }
            ],
        }
        with self.assertRaises(ConversionError):
            read_trello(raw)

    def test_unrecognized_trello_color_dropped_in_lenient_mode(self):
        raw = {
            "name": "Board",
            "lists": [{"id": "l1", "name": "To Do", "closed": False}],
            "cards": [
                {
                    "id": "c1",
                    "name": "Card",
                    "idList": "l1",
                    "labels": [{"name": "weird", "color": "mauve"}],
                }
            ],
        }
        board = read_trello(raw, lenient=True)
        self.assertEqual(board.lists[0].cards[0].labels, [Label(name="weird")])

    def test_unrecognized_markdown_color_falls_back_to_full_token_in_lenient_mode(self):
        text = "# Board\n\n## List\n\n- [ ] Card\n  - labels: bug:mauve\n"
        board = read_markdown(text, lenient=True)
        self.assertEqual(board.lists[0].cards[0].labels, [Label(name="bug:mauve")])

    def test_unrecognized_markdown_color_raises_in_strict_mode(self):
        text = "# Board\n\n## List\n\n- [ ] Card\n  - labels: bug:mauve\n"
        with self.assertRaises(ConversionError):
            read_markdown(text)


if __name__ == "__main__":
    unittest.main()
