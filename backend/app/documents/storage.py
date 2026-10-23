"""Stockage des fichiers déposés : dossier local ou stockage objet compatible S3."""

import asyncio
import shutil
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def delete_prefix(self, prefix: str) -> int: ...


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("Clé de stockage invalide")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    async def delete_prefix(self, prefix: str) -> int:
        """Efface tous les fichiers d'un dossier (« org/ » ou « org/projet/ »)."""
        folder = self._path(prefix.rstrip("/"))
        if folder == self.root.resolve() or not folder.is_dir():
            return 0
        files = [p for p in folder.rglob("*") if p.is_file()]
        await asyncio.to_thread(shutil.rmtree, folder, True)
        return len(files)


class S3Storage:
    def __init__(self) -> None:
        import boto3

        settings = get_settings()
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        """Crée le compartiment au premier dépôt (MinIO démarre sans compartiment)."""
        if self._bucket_ready:
            return
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)
        self._bucket_ready = True

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(self._ensure_bucket)
        await asyncio.to_thread(
            self.client.put_object, Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        return bytes(response["Body"].read())

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def delete_prefix(self, prefix: str) -> int:
        def run() -> int:
            count = 0
            pages = self.client.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=prefix
            )
            for page in pages:
                keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                if keys:
                    self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys})
                    count += len(keys)
            return count

        return await asyncio.to_thread(run)


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        settings = get_settings()
        _storage = (
            S3Storage()
            if settings.storage_backend == "s3"
            else LocalStorage(settings.storage_local_path)
        )
    return _storage
