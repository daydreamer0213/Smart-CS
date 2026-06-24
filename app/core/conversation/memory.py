"""Sliding window context management with tiktoken counting."""

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        total += len(_enc.encode(m.get("content", "")))
        total += 4  # role + message overhead
    return total


def build_context(
    history: list[dict],
    max_tokens: int = 2000,
    max_turns: int = 10,
) -> list[dict]:
    result = history[-max_turns * 2:]  # each turn = user + assistant
    while count_tokens(result) > max_tokens and len(result) > 2:
        result = result[2:]  # drop oldest turn
    return result
