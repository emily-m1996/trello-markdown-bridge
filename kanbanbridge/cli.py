import argparse
import json
import sys
from pathlib import Path

from .formats import read_markdown, read_trello, write_markdown, write_trello
from .model import ConversionError

FORMAT_BY_SUFFIX = {".json": "trello", ".md": "markdown", ".markdown": "markdown"}


def detect_format(path, explicit):
    if explicit:
        return explicit
    suffix = Path(path).suffix.lower()
    fmt = FORMAT_BY_SUFFIX.get(suffix)
    if fmt is None:
        raise ConversionError(f"cannot guess format from extension {suffix!r}; pass --from/--to explicitly")
    return fmt


def build_parser():
    parser = argparse.ArgumentParser(
        prog="kanbanbridge",
        description="Convert kanban board exports between Trello JSON and a plain Markdown format.",
    )
    parser.add_argument("input", help="path to the source board export")
    parser.add_argument("output", help="path to write the converted board to")
    parser.add_argument(
        "--from",
        dest="from_format",
        choices=["trello", "markdown"],
        help="source format (guessed from the input extension if omitted)",
    )
    parser.add_argument(
        "--to",
        dest="to_format",
        choices=["trello", "markdown"],
        help="target format (guessed from the output extension if omitted)",
    )
    parser.add_argument(
        "--lenient",
        action="store_true",
        help="tolerate missing fields, archived items, and bad dates instead of raising",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        from_format = detect_format(args.input, args.from_format)
        to_format = detect_format(args.output, args.to_format)

        source_text = Path(args.input).read_text(encoding="utf-8")
        if from_format == "trello":
            board = read_trello(json.loads(source_text), lenient=args.lenient)
        else:
            board = read_markdown(source_text, lenient=args.lenient)

        if to_format == "trello":
            output_text = json.dumps(write_trello(board), indent=2) + "\n"
        else:
            output_text = write_markdown(board)

        Path(args.output).write_text(output_text, encoding="utf-8")
    except ConversionError as exc:
        print(f"kanbanbridge: {exc}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, OSError) as exc:
        print(f"kanbanbridge: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
