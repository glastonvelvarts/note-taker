import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from .stt import STT_MODES


def _print_final(text: str, is_final: bool, speaker: str) -> None:
    if is_final:
        print(f"{speaker}: {text}", flush=True)


def _join(args: argparse.Namespace) -> None:
    from .bot import join_meeting

    try:
        collector = asyncio.run(
            join_meeting(args.meeting_url, args.profile, _print_final, args.stt)
        )
    except KeyboardInterrupt:
        return
    if not collector.entries:
        sys.exit("no speech was transcribed")


def _login(args: argparse.Namespace) -> None:
    from .login import login

    print(f"profile saved at {login(args.profile)}")


def _summarize(args: argparse.Namespace) -> None:
    from .summarize import summarize_transcript

    print(summarize_transcript(args.transcript.read_text(encoding="utf-8")))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="note-taker",
        description="Join Google Meet calls, transcribe them live and summarize them.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    commands = parser.add_subparsers(required=True)

    login = commands.add_parser("login", help="sign in to Google once per profile")
    login.add_argument("profile")
    login.set_defaults(run=_login)

    join = commands.add_parser("join", help="join a meeting and transcribe it")
    join.add_argument("meeting_url")
    join.add_argument("profile")
    join.add_argument("--stt", choices=STT_MODES, help="overrides STT_MODE")
    join.set_defaults(run=_join)

    summarize = commands.add_parser("summarize", help="summarize a saved transcript")
    summarize.add_argument("transcript", type=Path)
    summarize.set_defaults(run=_summarize)

    args = parser.parse_args()
    load_dotenv(find_dotenv(usecwd=True))
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if not args.verbose:
        logging.getLogger(__package__).setLevel(logging.INFO)
    try:
        args.run(args)
    except Exception as error:
        if args.verbose:
            raise
        sys.exit(f"error: {error}")


if __name__ == "__main__":
    main()
