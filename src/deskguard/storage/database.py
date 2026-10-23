"""Gerenciamento da conexão com o banco SQLite local."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from deskguard.storage.models import Base


class Database:
    """Acesso ao banco local.

    O SQLite é usado em modo local, com ``WAL`` habilitado e chaves
    estrangeiras ativas, o que dá integridade referencial às etapas de
    execução sem exigir um servidor de banco de dados.
    """

    def __init__(self, path: Path, *, echo: bool = False) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(
            f"sqlite:///{self.path.as_posix()}",
            echo=echo,
            future=True,
            connect_args={"check_same_thread": False},
        )
        self._configure(self.engine)
        self._session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, future=True
        )

    @staticmethod
    def _configure(engine: Engine) -> None:
        @event.listens_for(engine, "connect")
        def _set_pragma(dbapi_connection: object, _record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Sessão transacional: confirma em caso de sucesso, desfaz em erro."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()
