# RAG ingestion and citations implementation plan

Status: Proposed
Last updated: 2026-10-07

## 1. Purpose

Evolve the current CLI proof of concept into a reliable document-ingestion and
question-answering core that:

1. accepts documents without loading a large upload through the application;
2. ingests each document asynchronously and idempotently;
3. returns verifiable, page-level citations with every grounded answer; and
4. has enough tests, configuration, and observability to change safely.

This document is both the technical specification and the phased workplan. It
does not require a web UI. The core services should remain usable by the CLI and
be ready for a future HTTP API.

## 2. Current-state review

### What is already working

- PDF and text loading, recursive chunking, OpenAI embeddings, persisted Chroma
  storage, semantic retrieval, and answer generation are separated into small
  modules.
- The retriever limits context to four chunks and handles retrieval failures.
- Secrets and the chat model are environment-configured; local credentials and
  Chroma data are ignored by Git.
- The current source passes `mypy` and Python bytecode compilation.

### Gaps to address

| Priority | Finding | Impact |
| --- | --- | --- |
| P0 | `loader.py` replaces loader metadata with only `source` and `chunk_index`. | PDF page numbers and other provenance needed for citations are lost. |
| P0 | Retrieval returns one formatted string rather than retrieved document records. | The caller cannot reliably build, validate, or render citations. |
| P0 | Ingestion scans every local file and processes the entire batch in memory. | One bad or large document can fail the batch; there is no progress or retry boundary. |
| P0 | Chunk IDs derive from filenames and chunk positions. | Same-name files can collide; changed files can leave stale chunks; retries are not explicitly idempotent. |
| P1 | `main.py` creates the model and starts input at import time. | Unit testing and reuse from an API or worker are difficult. |
| P1 | Errors are converted to user-facing strings and include raw exception text. | Operational failures are hard to classify and may expose internal details. |
| P1 | There are no automated tests or retrieval/answer quality evaluations. | Regressions in ingestion, metadata, and grounding will be difficult to detect. |
| P1 | There is no score threshold or explicit abstention path before generation. | Irrelevant retrieved text can produce confident but unsupported answers. |
| P2 | Chroma is local and the workflow has no document/job registry. | Multiple workers, deployment, status reporting, deletion, and re-indexing are not supported. |

## 3. Target architecture

```text
CLI or future API
      |
      +-- create document record / request upload
      |          |
      |          +-- local file (development)
      |          +-- presigned S3 upload (hosted environments)
      |
      +-- enqueue ingestion by document_id
                    |
                 worker
                    |
        stream object to bounded temp file
                    |
        parse -> chunk -> embed in batches
                    |
        vector store + document/job status

question -> retrieve structured chunks -> build numbered context
         -> generate grounded answer -> validate/return citations
```

S3 solves durable storage and direct transfer; it does not by itself solve
large-document parsing. The worker must avoid reading the full object into
memory, batch embedding writes, report progress, and clean up temporary files.

## 4. Functional specification

### 4.1 Storage abstraction

Introduce a `DocumentStorage` protocol so local development does not require
AWS:

```python
class DocumentStorage(Protocol):
    def open(self, object_key: str) -> BinaryIO: ...
    def download_to(self, object_key: str, destination: Path) -> None: ...
    def delete(self, object_key: str) -> None: ...
```

Implementations:

- `LocalDocumentStorage` for the existing `sources/` workflow.
- `S3DocumentStorage` using `boto3`, private objects, server-side encryption,
  checksums, and a configured bucket/prefix.

For a future HTTP surface, the application creates a random object key such as
`documents/{document_id}/original`, then returns a short-lived presigned upload
URL. The client uploads directly to S3 and calls a completion endpoint. Do not
put the user-supplied filename in the authoritative key and do not accept an
arbitrary bucket/key from the client.

Use a single presigned `PUT` for ordinary files. Add multipart initiation,
part-URL signing, completion, and abort only when the supported file-size target
requires it. AWS recommends considering multipart upload at about 100 MB. Each
unfinished multipart upload must be aborted by the application or an S3
lifecycle rule.

Upload validation must include:

- allowed extension and detected content type (`.pdf`, `.txt` initially);
- a configurable maximum object size checked before signing and again with S3
  metadata before ingestion;
- checksum verification, normalized display filename, and tenant/user ownership;
- malware scanning before a document becomes eligible for ingestion in a
  production environment.

### 4.2 Document and ingestion lifecycle

Add a durable document/job registry before asynchronous workers. SQLite is
acceptable for a single-process milestone; PostgreSQL is the deployment target.

Minimum document fields:

```text
document_id (UUID)       owner_id / tenant_id
display_name             storage_provider, bucket, object_key
content_type, size_bytes checksum_sha256
status                   created_at, updated_at
error_code               error_message (sanitized)
index_version            chunk_count
```

Statuses:

```text
pending_upload -> uploaded -> queued -> processing -> ready
                                      \-> failed
ready -> deleting -> deleted
```

Ingestion operates on one `document_id`. It must be safe to retry:

1. claim a queued job with a lease;
2. download to a bounded temporary location;
3. parse and retain loader metadata;
4. normalize metadata and split content;
5. embed and write chunks in configurable batches;
6. atomically make the new `index_version` active;
7. delete chunks from superseded versions and remove the temporary file.

Stable chunk IDs use `{document_id}:{index_version}:{chunk_index}`. A checksum
can skip re-indexing identical content. Failures retain a sanitized error and
retry count; retry only transient failures automatically.

### 4.3 Citation model

Preserve and normalize provenance on every chunk:

```text
document_id, display_name, source_uri, page_number, chunk_index,
index_version, checksum_sha256
```

Page numbers presented to users are one-based. Text files may omit
`page_number`; their citation uses the filename and chunk number.

Change retrieval to return structured results, not a prompt-ready string:

```python
@dataclass(frozen=True)
class RetrievedChunk:
    citation_id: int
    document_id: str
    display_name: str
    page_number: int | None
    chunk_index: int
    text: str
    relevance_score: float | None

@dataclass(frozen=True)
class Citation:
    citation_id: int
    document_id: str
    display_name: str
    page_number: int | None
    chunk_index: int
    excerpt: str

@dataclass(frozen=True)
class Answer:
    text: str
    citations: list[Citation]
```

The prompt labels each context block `[1]`, `[2]`, and so on and instructs the
model to cite factual claims inline with only those labels. The response layer:

1. parses citation markers used by the answer;
2. rejects unknown markers;
3. returns only citations actually referenced, deduplicated in first-use order;
4. abstains when no chunks pass the configured relevance policy; and
5. prints an answer followed by a `Sources` list in the CLI.

Citation links should identify the application document, not expose permanent
S3 URLs. A future download/view endpoint can authorize the request and issue a
short-lived URL. For PDFs, it may add a `#page=N` fragment for compatible
viewers.

Acceptance examples:

- `Employees receive 25 leave days [1].` followed by
  `[1] policies.pdf, page 3`.
- If two chunks from the same page support an answer, the displayed source is
  deduplicated while internal chunk provenance remains available.
- If retrieval is empty or below threshold, the response says the available
  documents do not contain the answer and returns `citations=[]`.
- A citation marker can never refer to a chunk that was not retrieved for that
  request.

## 5. Non-functional requirements

- **Memory:** file transfer and embedding are bounded; batch sizes are
  configurable. Record peak-memory behavior in an integration test with a
  generated large text fixture.
- **Security:** least-privilege AWS role, private bucket, encryption in transit
  and at rest, short presigned URL lifetime, ownership checks, filename
  sanitization, and no raw internal exception text in user responses.
- **Reliability:** idempotent retries, per-document failure isolation, job
  leases/timeouts, multipart cleanup, and deletion of both object and vectors.
- **Observability:** structured logs with request/job/document IDs plus metrics
  for upload bytes, parse time, chunk count, embedding latency/cost, retrieval
  latency, failures, and citation/abstention rates.
- **Cost controls:** configurable size/page/chunk limits, embedding batches,
  duplicate checksum detection, and lifecycle cleanup for rejected uploads.
- **Configuration:** typed settings for model IDs, chunking, retrieval count and
  threshold, storage backend, bucket/region, limits, and timeouts. Validate
  settings at startup.

## 6. Delivery plan

### Milestone 0 — testable foundations (P0, small) — Done

- Move the interactive loop behind `main()` and `if __name__ == "__main__"`.
- Introduce typed settings and domain result/error types.
- Add `pytest` and unit tests for loaders, metadata preservation, retrieval, and
  answer formatting using fakes (no OpenAI calls).
- Add lint/type/test commands to the README or a task runner.

Definition of done: importing application modules has no network/input side
effects; CI-style checks run locally; current CLI behavior still works.

### Milestone 1 — trustworthy citations (P0, medium) — Done

- Preserve original PDF metadata and normalize one-based page numbers.
- Return `RetrievedChunk` records with scores from the retrieval layer.
- Add relevance/abstention policy and numbered prompt context.
- Return `Answer` with validated citations and render sources in the CLI.
- Add tests for page citations, duplicates, invalid markers, no results, and
  retrieval failures.

Definition of done: every grounded factual answer exposes only retrieved
sources, including a page number when available; unsupported answers abstain.

### Milestone 2 — per-document, idempotent ingestion (P0, medium) — Done

- Add document identity, checksum, status, and index-version records.
- Refactor loading/chunking to process a single document.
- Batch vector writes and support replace/delete by document and index version.
- Add retry, stale-version cleanup, and partial-failure integration tests.

Definition of done: rerunning a job does not duplicate chunks, replacing a
document leaves no active stale chunks, and one failed document does not block
another.

### Milestone 3 — S3 and background processing (P1, large)

- Add local/S3 storage adapters and AWS configuration.
- Treat the configured source bucket/prefix as an ingestion source: route S3
  `ObjectCreated` events (directly or through SQS) to the ingestion handler,
  validate bucket/key/size before download, and use the stable `s3://bucket/key`
  URI as the document identity.
- Add a minimal API for create-upload, complete-upload, status, and delete, or
  expose equivalent application-service methods if the API is deferred.
- Upload directly with short-lived presigned URLs; use multipart above the
  agreed threshold.
- Add a worker queue, temp-file cleanup, upload validation, and lifecycle rules.
- Test with an S3-compatible local service or AWS test environment.

Definition of done: a large file bypasses application request memory, progresses
through visible statuses, becomes queryable, and can be completely deleted; an
object uploaded to the configured S3 source bucket is ingested through the
event handler without requiring a local CLI run.

### Milestone 4 — quality and production readiness (P1/P2, medium)

- Create a small, versioned RAG evaluation set with expected source documents.
- Track retrieval recall, citation correctness, groundedness, abstention, cost,
  and latency before changing models, chunking, or search configuration.
- Replace the document-registry data-access code with an ORM and migrate the
  registry from SQLite to PostgreSQL. Deprecate the SQLite implementation,
  provide a migration path for existing registry data, and test the PostgreSQL
  integration.
- Make ChromaDB production-ready: externalize persistence and connection
  settings, configure collection and embedding-version management, add health
  checks and backup/restore guidance, and document the supported deployment
  topology and scaling limits.
- Replace the interactive CLI with a simple browser interface modeled on
  familiar chat applications: a primary chat/query view with cited responses
  and a left-hand sidebar for creating, selecting, and resuming chat history.
  Preserve the application-service boundary so the interface can call a
  versioned HTTP API rather than embedding business logic in the UI.
- Add structured logging/metrics, CI, dependency/security scanning, and
  production vector-store evaluation if horizontal scaling is required.

Definition of done: changes can be compared against a recorded quality and
performance baseline; the registry runs on PostgreSQL through the ORM;
ChromaDB is operable under the documented deployment model; users can query
and resume conversations in the browser; and operational failures are
diagnosable without exposing internal errors to users.

## 7. Recommended implementation order

Implement Milestones 0 and 1 first. Citations depend on metadata preservation
and structured retrieval, and those changes also establish the domain objects
needed by ingestion. Then implement Milestone 2 before S3: moving the current
all-files workflow to S3 without document identity and idempotency would only
relocate the files while retaining the main reliability problems.

Multipart upload, a distributed queue, PostgreSQL, malware scanning, and a
hosted vector database should be enabled by the design but added only when the
deployment and file-size requirements justify them.

## 8. Decisions needed before Milestone 3

These do not block Milestones 0–2:

1. Is the next product surface CLI-only, an HTTP API, or API plus browser UI?
2. What maximum file size and page count must be supported?
3. Is AWS the target deployment, and is S3 mandatory or should any S3-compatible
   provider work?
4. Is the application multi-user/multi-tenant, and who may view or delete each
   document?
5. What freshness target is acceptable between upload completion and a document
   becoming searchable?

## 9. Reference

- [AWS: presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [AWS: multipart upload limits](https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html)
