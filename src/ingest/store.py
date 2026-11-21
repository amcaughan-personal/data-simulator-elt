"""The raw zone in S3: rows as gzipped JSON lines, plus small JSON state objects."""

import gzip
import json
from typing import Any

import boto3


def encode_rows(rows: list[dict[str, Any]]) -> bytes:
    """One JSON object per line, gzipped: the format the Glue raw tables read."""
    return gzip.compress("".join(json.dumps(row) + "\n" for row in rows).encode())


class S3Store:
    def __init__(self, bucket: str, client: Any = None):
        self.bucket = bucket
        self.s3 = client or boto3.client("s3")

    def read_json(self, key: str) -> dict[str, Any] | None:
        try:
            body = self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.s3.exceptions.NoSuchKey:
            return None
        return json.loads(body)

    def write_json(self, key: str, value: dict[str, Any]) -> None:
        self.s3.put_object(
            Bucket=self.bucket, Key=key, Body=json.dumps(value).encode(), ContentType="application/json"
        )

    def write_rows(self, key: str, rows: list[dict[str, Any]], metadata: dict[str, str]) -> None:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=encode_rows(rows),
            ContentType="application/x-ndjson",
            ContentEncoding="gzip",
            Metadata=metadata,
        )
