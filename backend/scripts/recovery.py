"""Explicit backup/restore CLI; does not import runtime config or initialize a DB."""
import argparse
import json
from app.recovery import create_backup, restore_backup


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--database", required=True)
    backup.add_argument("--secret", required=True)
    backup.add_argument("--destination", required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--source", required=True)
    restore.add_argument("--destination", required=True)
    args = parser.parse_args()
    result = create_backup(args.database, args.secret, args.destination) if args.command == "backup" else restore_backup(args.source, args.destination)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
