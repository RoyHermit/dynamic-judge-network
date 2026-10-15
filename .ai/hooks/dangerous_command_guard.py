#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def split_unquoted_segments(command: str) -> list[str]:
    segments = []
    start = 0
    quote: str | None = None
    escaped = False
    for index, character in enumerate(command):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote != "'":
            escaped = True
            continue
        if character in {"'", '"'}:
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
            continue
        if quote is None and character in ";&|\n":
            segments.append(command[start:index])
            start = index + 1
    segments.append(command[start:])
    return segments


def is_recursive_force(flags: list[str]) -> bool:
    short_options = "".join(
        flag[1:].lower()
        for flag in flags
        if flag.startswith("-") and not flag.startswith("--")
    )
    return (
        "r" in short_options or "--recursive" in flags
    ) and ("f" in short_options or "--force" in flags)


def is_dangerous_target(target: str, cwd: str, repository_root: Path) -> bool:
    literal_targets = {
        "/",
        "~",
        "$HOME",
        "${HOME}",
        "$PWD",
        "${PWD}",
        ".",
        "./",
        "*",
        "./*",
    }
    if target in literal_targets:
        return True
    expanded_text = target.replace("${PWD}", cwd).replace("$PWD", cwd)
    expanded = Path(os.path.expandvars(os.path.expanduser(expanded_text)))
    home = Path.home().resolve()
    current = Path(cwd).resolve()
    resolved = (
        expanded.resolve(strict=False)
        if expanded.is_absolute()
        else (current / expanded).resolve(strict=False)
    )
    return resolved in {Path("/"), home, current, repository_root.resolve()}


def command_is_dangerous(
    command: str, cwd: str, repository_root: Path = REPOSITORY_ROOT
) -> bool:
    try:
        token_segments = [
            shlex.split(segment, posix=True)
            for segment in split_unquoted_segments(command)
        ]
    except ValueError:
        return False
    sudo_options_with_values = {
        "-C",
        "-D",
        "-g",
        "-h",
        "-p",
        "-r",
        "-t",
        "-u",
        "--chdir",
        "--close-from",
        "--command-timeout",
        "--group",
        "--host",
        "--prompt",
        "--role",
        "--type",
        "--user",
    }
    for tokens in token_segments:
        index = 0
        while (
            index < len(tokens)
            and (
                Path(tokens[index]).name in {"command", "env"}
                or (
                    "=" in tokens[index]
                    and tokens[index].split("=", maxsplit=1)[0].isidentifier()
                )
            )
        ):
            index += 1
        if index >= len(tokens):
            continue
        token = tokens[index]
        if Path(token).name == "sudo":
            index += 1
            while index < len(tokens):
                option = tokens[index]
                if option == "--":
                    index += 1
                    break
                if not option.startswith("-"):
                    break
                index += 2 if option in sudo_options_with_values else 1
            if index >= len(tokens):
                continue
            token = tokens[index]
        if Path(token).name == "rm":
            flags = []
            targets = []
            for item in tokens[index + 1 :]:
                if item.startswith("-"):
                    flags.append(item)
                else:
                    targets.append(item)
            if is_recursive_force(flags) and any(
                is_dangerous_target(target, cwd, repository_root) for target in targets
            ):
                return True
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        return 0
    command = payload.get("tool_input", {}).get("command")
    if not isinstance(command, str):
        return 0
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
    if command_is_dangerous(command, cwd):
        print(
            "Blocked destructive recursive delete of a broad protected target.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
