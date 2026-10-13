from app.ingestion.chunker import chunk_text


def test_chunk_text_carries_sentence_overlap_to_the_next_chunk():
    first = " ".join(["first"] * 20) + "."
    second = " ".join(["second"] * 20) + "."
    third = " ".join(["third"] * 20) + "."

    chunks = chunk_text(
        f"{first} {second} {third}",
        chunk_size=45,
        overlap_tokens=25,
    )

    assert len(chunks) >= 2
    assert "second" in chunks[0]
    assert "second" in chunks[1]
