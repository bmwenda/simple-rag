# Simple RAG product and delivery specification

Status: Active backlog

Last verified against code: 2026-10-07

## Purpose

Simple RAG provides grounded answers over organization documents. Every factual
answer must cite retrieved source content, and document ingestion must be safe
to retry without leaving duplicate or stale vector chunks.

This is the active specification and delivery backlog. Completed work is
described only as the current baseline; remaining work is an unchecked task so
it can be delivered and reviewed independently.

## Supported interfaces and constraints

- Supported document types are the extension allowlist in
  `src/document_types.py`, including PDF, plain text, Markdown, HTML, common
  Office formats, and structured text formats.
- The local CLI remains the query interface until the web interface is delivered.
- Runtime and local ingestion use PostgreSQL as the sole document-registry
  backend. Unit tests mock the registry or engine boundary; concurrent job
  claims are not yet in place.
- Chroma uses a local persistent directory; it has not been configured as a
  horizontally scalable production service.
- S3 events must flow through SQS to Lambda. Direct S3-to-Lambda invocation is
  deliberately rejected by the event parser.
- `MAX_DOCUMENT_SIZE_BYTES` defaults to 100 MiB (104,857,600 bytes) and can be
  configured per deployment.
- The current repository contains no upload/status/delete HTTP API, no browser
  UI, no authentication model, and no infrastructure-as-code.

## Architecture contract

```text
local source file ----------------------> ingestion service
                                                |
S3 source bucket -> SQS -> Lambda -----------+-> validate -> temp file
                                                |        -> parse -> chunk
                                                |        -> embed in batches
                                                |        -> Chroma + registry

browser UI (future) -> HTTP API (future) -> chat service -> retrieve -> answer
                                                        -> validated citations
```

Stable vector IDs use `{document_id}:{index_version}:{chunk_index}`. Citation
metadata must retain `document_id`, display name, source URI, page number when
available and index version. User-visible failures must remain
sanitized; raw backend exception details must not be returned to callers.

## Delivery backlog

### P0 — complete the durable ingestion lifecycle

- [ ] Enforce `MAX_DOCUMENT_SIZE_BYTES` consistently when issuing upload URLs
  and accepting uploads, in addition to the existing pre-download S3 check.
- [ ] Measure the end-to-end upload-to-searchable path for a 100 MB document
  and enforce the five-minute maximum. Define a bounded failure or retry outcome
  when the time budget cannot be met.
- [ ] Define the upload, processing, ready, failed, deleting, and deleted state
  transitions, including permitted retries and terminal-state behavior.
- [ ] Add a document storage abstraction with local and S3 implementations so
  ingestion no longer depends directly on a local path or an S3-specific type.
- [ ] Add an application service for creating an upload request, reporting
  document status, and deleting a document and its active vector chunks.
- [ ] Generate scoped, short-lived S3 upload URLs. Do not let callers choose an
  arbitrary bucket or object key.
- [ ] Add multipart upload initiation, part signing, completion, abort, and
  lifecycle cleanup when the configured upload-size threshold requires it.
- [ ] Validate file extension, detected content type, object size, checksum,
  and normalized display name before indexing. Define the malware-scanning
  integration point before a document becomes eligible for ingestion.
- [ ] Delete the S3 object, every indexed chunk version, and the registry record
  through a recoverable document-deletion workflow.

Definition of done: one document can be uploaded, tracked, retried, queried,
and deleted without an orphaned S3 object, registry record, or vector chunk.

### P1 — operationalize S3, SQS, and Lambda

- [ ] Add Terraform modules for the private source bucket, SQS queue, Lambda
  event-source mapping, dead-letter queue, encryption, and least-privilege IAM
  roles.
- [ ] Configure S3 object-created notifications with the approved prefix and
  the supported-document extension filters, delivering only to the ingestion
  queue.
- [ ] Add partial-batch SQS failure reporting so successfully processed records
  are not retried with failed records.
- [ ] Set and document queue visibility timeout, Lambda timeout, retry policy,
  concurrency limits, DLQ retention, and alarms based on the supported maximum
  document size and five-minute searchable-status requirement.
- [ ] Configure Lambda memory and ephemeral storage for the configured 100 MB
  default download and parsing workload, and verify the setting under the
  five-minute time budget.
- [ ] Add structured logs containing document and SQS message identifiers, with
  sanitized error codes and no document content or credentials.
- [ ] Add metrics and alarms for queue age, DLQ depth, ingest success/failure,
  object size, parse duration, chunk count, embedding latency, and retries.
- [ ] Add integration coverage against AWS or an S3/SQS-compatible environment
  for the complete S3 -> SQS -> Lambda event path.
- [ ] Add a generated large-document integration test that records bounded
  memory behavior and enforces the configured object-size limit.

Definition of done: the deployed event path is observable, retriable, and
operable without direct S3-to-Lambda delivery or manual local ingestion.

### P1 — migrate the document registry to PostgreSQL

- [x] Select SQLAlchemy and Alembic for ORM persistence and schema migrations.
- [ ] Model ingestion jobs, attempts, leases, and ownership boundaries.
- [x] Replace direct registry storage access in `DocumentRegistry` with
  repository code backed by the ORM.
- [x] Add PostgreSQL configuration, startup validation, and health checks.
- [x] Manage the registry schema with Alembic migrations.
- [ ] Use transactional job claims and leases so multiple workers cannot index
  the same document version concurrently.
- [x] Use PostgreSQL for the registry in hosted and local development;
  unit tests use fakes or mocks instead of a database.
- [ ] Add PostgreSQL-backed integration tests for idempotency, concurrent job
  claims, retry behavior, startup validation, and health checks.

Definition of done: production ingestion state is stored and coordinated in
PostgreSQL.

### P1 — make vector storage production-ready

- [ ] Define the supported Chroma deployment topology, persistence location,
  backup/restore process, and horizontal-scaling limits.
- [ ] Externalize Chroma connection, authentication, collection, and persistence
  settings; validate them at startup.
- [ ] Version collections and embedding models so re-embedding can run without
  mixing incompatible vectors in one active collection.
- [ ] Add vector-store health checks and a documented recovery procedure for
  failed writes, stale versions, and restore operations.
- [ ] Evaluate and document the migration threshold to a hosted vector service
  if Chroma cannot meet availability, scale, or tenancy requirements.

Definition of done: operators can deploy, validate, back up, restore, and
re-index the vector store according to documented limits.

### P1 — introduce an HTTP API and browser chat experience

- [ ] Define a versioned HTTP API for query, upload request, upload completion,
  document status, document deletion, and health checks.
- [ ] Keep chat, retrieval, ingestion, and citation logic in application
  services; HTTP handlers and UI components must not duplicate that logic.
- [ ] Replace the interactive CLI as the primary user interface with a simple
  browser chat page that renders answer citations and safe error states.
- [ ] Add a left sidebar that creates, lists, selects, renames, and resumes chat
  conversations.
- [ ] Persist chat history with a clear retention policy and bind it to an
  authenticated single user once identity is introduced.
- [ ] Add responsive, keyboard-accessible UI behavior and loading, empty, and
  failed-state designs.
- [ ] Deprecate CLI interface and remove all references and uses from code base.

Definition of done: a user can upload a document, observe its status, query it,
inspect citations, and resume a prior conversation through the browser.

### P2 — quality, security, and release controls

- [ ] Create a versioned evaluation set with expected documents, answers,
  citations, abstentions, and adversarial/ambiguous queries.
- [ ] Record retrieval recall, citation correctness, groundedness, abstention,
  latency, and embedding/model cost for every material retrieval or prompt
  change.
- [ ] Add dependency, secret, and static-security scanning to CI; fail builds
  on defined severity thresholds.
- [ ] Add authentication, single-user authorization, and audit logging before
  storing documents or chat history.
- [ ] Implement chat-history retention so content is automatically purged no
  later than 30 days after the applicable deletion event. Define whether a user
  deletion hides content immediately and whether any recovery window is allowed.
- [ ] Define document retention, deletion, privacy, and incident-response
  policies before production data is accepted.
- [ ] Add rate limiting, request size limits, model usage limits, and spend
  alerts for public or multi-user deployment.
- [ ] Produce a deployment runbook covering configuration, migrations, rollback,
  backups, DLQ handling, vector recovery, and incident triage.

Definition of done: releases can be assessed against a recorded quality baseline
and operated securely without exposing internal failures to end users.

## Confirmed decisions and requirements

- The default maximum file size is 100 MB and is configurable with
  `MAX_DOCUMENT_SIZE_BYTES`. Deployments must set the limit deliberately and
  enforce it at every upload and ingestion boundary.
- A document must become searchable within five minutes of upload completion.
- AWS is the supported cloud provider.
- Terraform is the infrastructure-as-code tool.
- The first browser release is for one authenticated user; multi-tenancy is out
  of scope.
- Chat history may be retained for no more than 30 days after its applicable
  deletion event. Deleted content should immediately become inaccessible
- Availability and reliability should be cost-aware rather than over-engineered.
  The measurable availability, recovery-time, recovery-point, and queue-delay
  targets still need to be set before infrastructure work begins.

## References

- [S3 source-bucket ingestion](s3-ingestion.md)
- [AWS S3 event notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html)
- [AWS Lambda with SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
