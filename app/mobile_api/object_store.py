from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UploadTarget:
    url: str
    method: str = "PUT"
    headers: dict[str, str] | None = None
    direct: bool = False


class LocalObjectStore:
    supports_proxy_upload = True

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def upload_target(self, object_key: str, content_type: str, *, proxy_url: str) -> UploadTarget:
        return UploadTarget(url=proxy_url, headers={"content-type": content_type}, direct=False)

    def path(self, object_key: str) -> Path:
        root = self.root.resolve()
        target = (root / object_key).resolve()
        if root not in target.parents:
            raise ValueError("unsafe object key")
        return target

    def exists(self, object_key: str) -> bool:
        return self.path(object_key).is_file()

    def size(self, object_key: str) -> int:
        return self.path(object_key).stat().st_size

    def materialize(self, object_key: str, target: str | Path) -> Path:
        source = self.path(object_key)
        destination = Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        return destination

    def delete(self, object_key: str) -> None:
        target = self.path(object_key)
        if target.exists():
            target.unlink()


class S3ObjectStore:
    """S3-compatible adapter suitable for COS, AWS S3, and MinIO."""

    supports_proxy_upload = False

    def __init__(
        self,
        *,
        bucket: str,
        region: str = "",
        endpoint_url: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        session_token: str = "",
        prefix: str = "mochi-scout",
        presign_ttl_seconds: int = 900,
    ) -> None:
        if not bucket:
            raise ValueError("MOBILE_S3_BUCKET is required for s3 object storage")
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - production extra
            raise RuntimeError("S3 object storage requires the mobile-prod dependency extra") from exc
        kwargs: dict[str, Any] = {}
        if region:
            kwargs["region_name"] = region
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if access_key_id:
            kwargs["aws_access_key_id"] = access_key_id
        if secret_access_key:
            kwargs["aws_secret_access_key"] = secret_access_key
        if session_token:
            kwargs["aws_session_token"] = session_token
        self.client = boto3.client("s3", **kwargs)
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.presign_ttl_seconds = max(60, min(presign_ttl_seconds, 3600))

    def upload_target(self, object_key: str, content_type: str, *, proxy_url: str) -> UploadTarget:
        key = self._key(object_key)
        headers = {"content-type": content_type}
        url = self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=self.presign_ttl_seconds,
            HttpMethod="PUT",
        )
        return UploadTarget(url=url, headers=headers, direct=True)

    def exists(self, object_key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(object_key))
            return True
        except self.client.exceptions.ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def size(self, object_key: str) -> int:
        result = self.client.head_object(Bucket=self.bucket, Key=self._key(object_key))
        return int(result["ContentLength"])

    def materialize(self, object_key: str, target: str | Path) -> Path:
        destination = Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, self._key(object_key), str(destination))
        return destination

    def delete(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._key(object_key))

    def _key(self, object_key: str) -> str:
        clean = object_key.replace("\\", "/").lstrip("/")
        if ".." in clean.split("/"):
            raise ValueError("unsafe object key")
        return f"{self.prefix}/{clean}" if self.prefix else clean

