from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from app.database.schema import CONNECTION_PRAGMAS, MIGRATIONS, SCHEMA_VERSION

_READER_POOL_SIZE: int = 4


class Database:
    def __init__(self, database_path: Path, reader_pool_size: int = _READER_POOL_SIZE):
        self._database_path = database_path
        self._reader_pool_size = max(1, reader_pool_size)
        self._writer: aiosqlite.Connection | None = None
        self._writer_lock = asyncio.Lock()
        self._readers: asyncio.LifoQueue[aiosqlite.Connection] = asyncio.LifoQueue()
        self._all_readers: list[aiosqlite.Connection] = []

    async def _open_connection(self, *, read_only: bool) -> aiosqlite.Connection:
        connection = await aiosqlite.connect(self._database_path, isolation_level=None)
        connection.row_factory = aiosqlite.Row
        for pragma in CONNECTION_PRAGMAS:
            await connection.execute(pragma)
        if read_only:
            await connection.execute("PRAGMA query_only=ON")
        return connection

    async def connect(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._writer = await self._open_connection(read_only=False)
        os.chmod(self._database_path, 0o600)
        await self._apply_migrations()
        for _ in range(self._reader_pool_size):
            reader = await self._open_connection(read_only=True)
            self._all_readers.append(reader)
            self._readers.put_nowait(reader)

    async def _apply_migrations(self) -> None:
        assert self._writer is not None
        async with self._writer.execute("PRAGMA user_version") as cursor:
            row = await cursor.fetchone()
        current_version = int(row[0]) if row else 0

        for version_index in range(current_version, min(SCHEMA_VERSION, len(MIGRATIONS))):
            await self._writer.execute("BEGIN IMMEDIATE")
            try:
                for statement in MIGRATIONS[version_index]:
                    await self._writer.execute(statement)
                await self._writer.execute(f"PRAGMA user_version={version_index + 1}")
                await self._writer.execute("COMMIT")
            except BaseException:
                await self._writer.execute("ROLLBACK")
                raise

    async def close(self) -> None:
        for reader in self._all_readers:
            await reader.close()
        self._all_readers.clear()
        while not self._readers.empty():
            self._readers.get_nowait()
        if self._writer is not None:
            await self._writer.execute("PRAGMA optimize")
            await self._writer.close()
            self._writer = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        if self._writer is None:
            raise RuntimeError("database is not connected")
        async with self._writer_lock:
            await self._writer.execute("BEGIN IMMEDIATE")
            try:
                yield self._writer
            except BaseException:
                await self._writer.execute("ROLLBACK")
                raise
            await self._writer.execute("COMMIT")

    @asynccontextmanager
    async def reader(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = await self._readers.get()
        try:
            yield connection
        finally:
            self._readers.put_nowait(connection)

    async def fetch_all(self, statement: str, parameters: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        async with self.reader() as connection, connection.execute(statement, parameters) as cursor:
            return list(await cursor.fetchall())

    async def fetch_one(self, statement: str, parameters: Sequence[Any] = ()) -> aiosqlite.Row | None:
        async with self.reader() as connection, connection.execute(statement, parameters) as cursor:
            return await cursor.fetchone()

    async def fetch_scalar(self, statement: str, parameters: Sequence[Any] = ()) -> Any:
        row = await self.fetch_one(statement, parameters)
        return row[0] if row is not None else None

    async def execute(self, statement: str, parameters: Sequence[Any] = ()) -> int:
        async with self.transaction() as connection:
            cursor = await connection.execute(statement, parameters)
            return cursor.rowcount

    async def execute_returning_id(self, statement: str, parameters: Sequence[Any] = ()) -> int:
        async with self.transaction() as connection:
            cursor = await connection.execute(statement, parameters)
            return int(cursor.lastrowid or 0)

    async def execute_many(self, statement: str, parameter_sets: Iterable[Sequence[Any]]) -> None:
        async with self.transaction() as connection:
            await connection.executemany(statement, parameter_sets)
