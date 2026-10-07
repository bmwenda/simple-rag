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
    assert chunk_ids == ["handbook_pdf:0:0"]
    assert chunks[0].metadata == {
        "page": 2,
        "producer": "test",
        "document_id": "handbook_pdf",
        "display_name": "handbook.pdf",
        "source": str(source),
        "index_version": 0,
        "chunk_index": 0,
        "page_number": 3,
    }


def test_load_and_chunk_sources_ignores_directories(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()

    chunks, chunk_ids, source_files = loader.load_and_chunk_sources(str(tmp_path))

    assert chunks == []
    assert chunk_ids == []
    assert source_files == []


def test_load_file_uses_generic_loader_for_markdown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "handbook.md"
    source.write_text("# Handbook", encoding="utf-8")
    calls: list[str] = []

    class FakeLoader:
        def __init__(self, *, file_path: str) -> None:
            calls.append(file_path)

        def load(self) -> list[Document]:
            return [Document(page_content="Handbook", metadata={})]

    monkeypatch.setattr(loader, "DoclingLoader", FakeLoader)

    assert loader._load_file(str(source))[0].page_content == "Handbook"
    assert calls == [str(source)]


def test_load_file_rejects_unallowlisted_extensions(tmp_path: Path) -> None:
    source = tmp_path / "program.bin"
    source.write_bytes(b"not a document")

    try:
        loader._load_file(str(source))
    except RuntimeError as error:
        assert str(error) == "Unsupported document type"
    else:
        raise AssertionError("Expected unsupported files to be rejected")
