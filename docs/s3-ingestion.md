# S3 source-bucket ingestion

The application can ingest documents uploaded to one private S3 source bucket.
It accepts `.pdf` and `.txt` objects from the configured prefix, reads object
metadata before downloading, rejects objects larger than the configured limit,
and streams the object to a temporary file. The temporary filename is never
used as the document identity: the registry tracks `s3://<bucket>/<key>`, so a
new upload at the same key replaces the prior index version.

## Configuration

Set the following environment variables in the Lambda/worker environment:

```text
S3_SOURCE_BUCKET=company-rag-sources
S3_SOURCE_PREFIX=incoming
AWS_REGION=eu-west-1
MAX_DOCUMENT_SIZE_BYTES=104857600
```

`S3_SOURCE_PREFIX` may be empty to allow the whole bucket. The execution role
needs `s3:GetObject` and `s3:HeadObject` on the configured bucket and prefix,
plus read/write access to the configured vector store and document registry.
Keep the bucket private and enable server-side encryption.

## Event delivery

Deploy `src.s3_ingestion_handler.lambda_handler` as the worker entrypoint.
Configure an S3 event notification for `s3:ObjectCreated:*`, filtered to the
configured prefix and the `.pdf`/`.txt` suffixes. The handler accepts native S3
event payloads and S3 messages delivered through SQS, so S3-to-SQS-to-Lambda is
the recommended production topology for buffering and retry control.

For SQS delivery, configure a dead-letter queue and set the Lambda visibility
timeout longer than the largest expected document ingestion time. The handler
returns a compact status payload and never returns raw exception details.

## Local verification

Unit tests use an in-memory S3 client fake; no AWS credentials or network calls
are required. Before deployment, verify the bucket notification, IAM role, and
SQS retry/DLQ behavior in an AWS account or an S3-compatible integration test
environment.
