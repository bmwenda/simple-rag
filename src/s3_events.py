import json
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import unquote_plus


@dataclass(frozen=True)
class S3ObjectCreatedEvent:
    bucket: str
    key: str


def sqs_s3_object_created_events(
    payload: dict[str, object],
) -> Iterable[S3ObjectCreatedEvent]:
    """Yield object-created records from S3 notifications delivered by SQS."""
    records = payload.get("Records", [])
    if not isinstance(records, list):
        raise TypeError("SQS event Records must be a list")

    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("eventSource") != "aws:sqs":
            raise ValueError("S3 ingestion accepts only SQS-delivered events")
        body = record.get("body")
        if not isinstance(body, str):
            raise TypeError("SQS event body must be a JSON string")
        decoded = json.loads(body)
        if not isinstance(decoded, dict):
            raise TypeError("SQS event body must be a JSON object")
        yield from _s3_object_created_events(decoded)


def _s3_object_created_events(
    payload: dict[str, object],
) -> Iterable[S3ObjectCreatedEvent]:
    records = payload.get("Records", [])
    if not isinstance(records, list):
        raise TypeError("S3 event Records must be a list")

    for record in records:
        if not isinstance(record, dict):
            continue
        event_name = record.get("eventName")
        s3 = record.get("s3")
        if not isinstance(event_name, str) or not event_name.startswith("ObjectCreated:"):
            continue
        if not isinstance(s3, dict):
            raise TypeError("S3 event record has no S3 object")
        bucket = s3.get("bucket")
        object_data = s3.get("object")
        if not isinstance(bucket, dict) or not isinstance(object_data, dict):
            raise TypeError("S3 event record is incomplete")
        bucket_name = bucket.get("name")
        encoded_key = object_data.get("key")
        if not isinstance(bucket_name, str) or not isinstance(encoded_key, str):
            raise TypeError("S3 event record has no bucket or object key")
        yield S3ObjectCreatedEvent(bucket=bucket_name, key=unquote_plus(encoded_key))
