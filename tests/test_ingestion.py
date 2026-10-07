from pathlib import Path

from langchain_core.documents import Document

from src.config import Settings
from src.document_registry import DocumentRegistry
from src.domain import DocumentStatus
from src.ingestion import DocumentIngestionService


class FakeVectorStore:
    def __init__(
        self,
        *,
        fail_on_add_calls: set[int] | None = None,
    ) -> None:
        self.add_calls: list[tuple[list[Document], list[str]]] = []
        self.delete_calls: list[list[str]] = []
        self._fail_on_add_calls = fail_on_add_calls or set()

    def add_documents(self, documents: list[Document], **kwargs: object) -> list[str]:
        raw_ids = kwargs["ids"]
        assert isinstance(raw_ids, list)
        ids = [str(chunk_id) for chunk_id in raw_ids]
        self.add_calls.append((documents, ids))
        if len(self.add_calls) in self._fail_on_add_calls:
            raise RuntimeError("vector store unavailable")
        return ids

    def delete(self, ids: list[str]) -> None:
        self.delete_calls.append(ids)


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "openai_api_key": "test-key",
        "openai_model": "test-model",
        "document_registry_path": tmp_path / "documents.sqlite3",
        "chunk_size": 20,
        "chunk_overlap": 0,
        "embedding_batch_size": 100,
        "ingestion_max_attempts": 2,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def make_service(
    tmp_path: Path,
    store: FakeVectorStore,
    **settings_overrides: object,
) -> tuple[DocumentIngestionService, DocumentRegistry]:
    settings = make_settings(tmp_path, **settings_overrides)
    registry = DocumentRegistry(settings.document_registry_path)
    return DocumentIngestionService(settings, registry, store), registry


def write_source(tmp_path: Path, name: str, content: str) -> Path:
    source = tmp_path / name
    source.write_text(content, encoding="utf-8")
    return source


def test_ingest_source_creates_ready_versioned_document(tmp_path: Path) -> None:
    source = write_source(tmp_path, "handbook.txt", "annual leave policy details")
    store = FakeVectorStore()
    service, registry = make_service(tmp_path, store)

    result = service.ingest_source(str(source))

    document = result.document
    assert result.indexed is True
    assert document.status is DocumentStatus.READY
    assert document.index_version == 1
    assert document.chunk_count == 2
    assert document.size_bytes == source.stat().st_size
    assert len(document.checksum_sha256) == 64
    assert store.add_calls[0][1] == [
        f"{document.document_id}:1:0",
        f"{document.document_id}:1:1",
    ]
    assert registry.get(document.document_id) == document


def test_ingest_source_skips_unchanged_ready_document(tmp_path: Path) -> None:
    source = write_source(tmp_path, "handbook.txt", "annual leave policy details")
    store = FakeVectorStore()
    service, _ = make_service(tmp_path, store)

    first = service.ingest_source(str(source))
    second = service.ingest_source(str(source))

    assert first.indexed is True
    assert second.indexed is False
    assert second.document.document_id == first.document.document_id
    assert len(store.add_calls) == 1


def test_ingest_source_replaces_changed_version_and_deletes_old_chunks(
    tmp_path: Path,
) -> None:
    source = write_source(tmp_path, "handbook.txt", "annual leave policy details")
    store = FakeVectorStore()
    service, _ = make_service(tmp_path, store)
    first = service.ingest_source(str(source))
    source.write_text("updated handbook content", encoding="utf-8")

    second = service.ingest_source(str(source))

    assert second.indexed is True
    assert second.document.document_id == first.document.document_id
    assert second.document.index_version == 2
    assert store.delete_calls == [
        [f"{first.document.document_id}:1:{index}" for index in range(2)]
    ]
    assert all(
        chunk_id.startswith(f"{first.document.document_id}:2:")
        for chunk_id in store.add_calls[-1][1]
    )


def test_ingest_source_retries_transient_vector_failure(tmp_path: Path) -> None:
    source = write_source(tmp_path, "handbook.txt", "annual leave policy details")
    store = FakeVectorStore(fail_on_add_calls={1})
    service, _ = make_service(tmp_path, store)

    result = service.ingest_source(str(source))

    assert result.indexed is True
    assert result.document.status is DocumentStatus.READY
    assert result.document.retry_count == 1
    assert len(store.add_calls) == 2


def test_ingest_source_cleans_partial_new_version_when_retries_are_exhausted(
    tmp_path: Path,
) -> None:
    source = write_source(tmp_path, "handbook.txt", "annual leave policy details")
    store = FakeVectorStore(fail_on_add_calls={2})
    service, _ = make_service(
        tmp_path,
        store,
        embedding_batch_size=1,
        ingestion_max_attempts=1,
    )

    result = service.ingest_source(str(source))

    assert result.indexed is False
    assert result.document.status is DocumentStatus.FAILED
    assert result.document.error_code == "RuntimeError"
    assert store.delete_calls == [
        [
            f"{result.document.document_id}:1:0",
            f"{result.document.document_id}:1:1",
        ]
    ]


def test_ingest_sources_isolates_failed_documents(tmp_path: Path) -> None:
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    write_source(sources_dir, "broken.bin", "not supported")
    write_source(sources_dir, "handbook.txt", "annual leave policy details")
    store = FakeVectorStore()
    service, _ = make_service(tmp_path, store)

    results = service.ingest_sources(str(sources_dir))

    assert [
        (result.document.display_name, result.document.status) for result in results
    ] == [
        ("broken.bin", DocumentStatus.FAILED),
        ("handbook.txt", DocumentStatus.READY),
    ]
    assert results[0].document.error_code == "RuntimeError"
    assert results[1].indexed is True
