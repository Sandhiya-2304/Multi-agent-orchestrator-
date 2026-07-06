import re


def _split_oversized_paragraph(paragraph: str, chunk_size: int) -> list[str]:
    """Split a too-long paragraph on line boundaries rather than blind
    character offsets, so a table/CSV row (one row = one line) never gets
    torn in half across two chunks -- that would corrupt the row's data and
    make it unretrievable in full for either chunk."""
    lines = paragraph.split("\n")
    pieces: list[str] = []
    current = ""

    for line in lines:
        if len(line) > chunk_size:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(line[i:i + chunk_size] for i in range(0, len(line), chunk_size))
            continue

        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            pieces.append(current)
            current = line

    if current:
        pieces.append(current)
    return pieces


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    """Paragraph-aware greedy chunker: packs paragraphs into character windows
    with trailing overlap carried into the next chunk. No tokenizer dependency
    -- adequate for this project's scale."""
    normalized = re.sub(r"\r\n?", "\n", text or "").strip()
    if not normalized:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalized) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        # Hard-split a paragraph that alone exceeds chunk_size.
        pieces = (
            _split_oversized_paragraph(paragraph, chunk_size)
            if len(paragraph) > chunk_size
            else [paragraph]
        )
        for piece in pieces:
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate) <= chunk_size:
                current = candidate
                continue

            chunks.append(current.strip())
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n\n{piece}".strip() if tail else piece

    if current.strip():
        chunks.append(current.strip())

    return chunks
