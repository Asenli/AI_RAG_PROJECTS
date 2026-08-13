"""Token-aware text chunking shared by upload and batch ingestion."""
from __future__ import annotations

import re
from functools import lru_cache

from tokenizers import Tokenizer

EMBEDDING_TOKENIZER = "BAAI/bge-large-zh-v1.5"
CHUNK_SIZE_TOKENS = 400
CHUNK_OVERLAP_TOKENS = 50


@lru_cache(maxsize=1)
def _tokenizer() -> Tokenizer:
    """Load the tokenizer that matches the configured BGE embedding model."""
    return Tokenizer.from_pretrained(EMBEDDING_TOKENIZER)


def token_count(text: str) -> int:
    return len(_tokenizer().encode(text, add_special_tokens=False).ids)


def split_text_by_tokens(
    text: str,
    chunk_size: int = CHUNK_SIZE_TOKENS,
    chunk_overlap: int = CHUNK_OVERLAP_TOKENS,
) -> list[str]:
    """Split text into chunks no longer than ``chunk_size`` tokens.

    Paragraphs are kept together where possible. Every chunk after the first
    starts with the final ``chunk_overlap`` tokens from its predecessor.
    """
    if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_size must be positive and overlap must be smaller")

    tokenizer = _tokenizer()
    token_ids = tokenizer.encode(text.strip(), add_special_tokens=False).ids
    if len(token_ids) <= chunk_size:
        return [text.strip()] if text.strip() else []

    # Reserve room for the overlap in all chunks after the first.
    new_token_limit = chunk_size - chunk_overlap
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    groups: list[list[int]] = []
    current: list[int] = []

    for paragraph in paragraphs:
        paragraph_ids = tokenizer.encode(paragraph, add_special_tokens=False).ids
        if len(paragraph_ids) > new_token_limit:
            if current:
                groups.append(current)
                current = []
            for start in range(0, len(paragraph_ids), new_token_limit):
                groups.append(paragraph_ids[start : start + new_token_limit])
            continue
        if current and len(current) + len(paragraph_ids) > new_token_limit:
            groups.append(current)
            current = []
        current.extend(paragraph_ids)

    if current:
        groups.append(current)

    chunks: list[str] = []
    previous: list[int] = []
    for group in groups:
        prefix = previous[-chunk_overlap:] if previous else []
        chunk_ids = prefix + group
        chunks.append(tokenizer.decode(chunk_ids, skip_special_tokens=True).strip())
        previous = chunk_ids
    return [chunk for chunk in chunks if chunk]
