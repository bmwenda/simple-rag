from pathlib import Path

from langchain_core.documents import Document

from src import loader


def test_load_and_chunk_sources_preserves_loader_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "handbook.pdf"
    source.touch()
    monkeypatch.setattr(
        loader,
        "_load_file",
        lambda path: [
            Document(
                page_content="Leave policy details",
                metadata={"page": 2, "producer": "test"},
            )
        ],
    )

    chunks, chunk_ids, source_files = loader.load_and_chunk_sources(
        str(tmp_path),
        chunk_size=100,
        chunk_overlap=10,
    )

    assert source_files == ["handbook.pdf"]
    assert chunk_ids == ["handbook_pdf-0"]
    assert chunks[0].metadata == {
        "page": 2,
        "producer": "test",
        "document_id": "handbook_pdf",
        "display_name": "handbook.pdf",
        "source": str(source),
        "chunk_index": 0,
        "page_number": 3,
    }


def test_load_and_chunk_sources_ignores_directories(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()

    chunks, chunk_ids, source_files = loader.load_and_chunk_sources(str(tmp_path))

    assert chunks == []
    assert chunk_ids == []
    assert source_files == []
