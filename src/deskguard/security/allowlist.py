"""Controle de destinos autorizados para as sondagens de rede.

O DeskGuard nunca sonda um destino que o operador não tenha declarado de
forma explícita. A lista vive em um arquivo JSON no diretório de dados da
plataforma e é consultada em dois momentos independentes:

1. na validação de parâmetros, que recusa a requisição **antes** de qualquer
   coleta (resposta 422 na API);
2. dentro do script PowerShell, que revalida a lista **antes** de emitir
   qualquer pacote de rede.

A duplicação é deliberada: ela protege a camada de coleta mesmo que o
arquivo seja alterado entre a validação e a execução.

Formato do arquivo (``allowed_targets.json``)::

    {
      "targets": [
        {"host": "intranet.corp.local", "ports": [80, 443],
         "description": "Portal corporativo"},
        {"host": "10.0.0.5", "ports": [3389], "ping": false,
         "description": "Servidor de acesso remoto"}
      ]
    }

Uma lista simples de nomes também é aceita: ``["intranet.corp.local"]``.

Regras aplicadas:

* no máximo :data:`MAX_TARGETS` destinos;
* no máximo :data:`MAX_PORTS_PER_TARGET` portas por destino;
* portas dentro da faixa 1–65535;
* nomes de host válidos conforme :data:`HOSTNAME_PATTERN` (sem curingas, sem
  barras, sem espaços, sem CIDR);
* a lista começa vazia — sem autorização explícita, nenhuma sondagem externa
  é feita.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ALLOWLIST_FILENAME = "allowed_targets.json"
ENV_ALLOWLIST_PATH = "DESKGUARD_ALLOWED_TARGETS_FILE"

MAX_TARGETS = 10
MAX_PORTS_PER_TARGET = 5
DEFAULT_PORTS: tuple[int, ...] = (80, 443)

HOSTNAME_PATTERN = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]{0,251}[A-Za-z0-9])?$")
IPV4_PATTERN = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


class AllowlistError(ValueError):
    """Erro de configuração da lista de destinos autorizados."""


def is_valid_host(host: str) -> bool:
    """Informa se o texto é um nome de host ou endereço IPv4 aceitável."""
    if not host or len(host) > 253:
        return False
    if IPV4_PATTERN.match(host):
        return all(0 <= int(part) <= 255 for part in IPV4_PATTERN.match(host).groups())
    return bool(HOSTNAME_PATTERN.match(host))


def is_ip_literal(host: str) -> bool:
    """Informa se o host é um endereço IPv4 literal (não exige resolução DNS)."""
    match = IPV4_PATTERN.match(host)
    return bool(match) and all(0 <= int(part) <= 255 for part in match.groups())


@dataclass(frozen=True, slots=True)
class AllowedTarget:
    """Um destino autorizado a ser sondado."""

    host: str
    ports: tuple[int, ...] = DEFAULT_PORTS
    description: str = ""
    ping: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "ports": list(self.ports),
            "description": self.description,
            "ping": self.ping,
        }


@dataclass(frozen=True, slots=True)
class TargetAllowlist:
    """Resultado da leitura da lista de destinos autorizados."""

    targets: tuple[AllowedTarget, ...] = ()
    path: Path | None = None
    available: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def is_empty(self) -> bool:
        return not self.targets

    def hosts(self) -> tuple[str, ...]:
        return tuple(target.host for target in self.targets)

    def find(self, host: str) -> AllowedTarget | None:
        normalized = host.strip().lower()
        for target in self.targets:
            if target.host == normalized:
                return target
        return None

    def allows(self, host: str) -> bool:
        return self.find(host) is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path) if self.path else None,
            "available": self.available,
            "count": len(self.targets),
            "targets": [target.to_dict() for target in self.targets],
            "warnings": list(self.warnings),
        }


def default_allowlist_path() -> Path:
    """Caminho do arquivo de destinos autorizados.

    A variável de ambiente tem precedência; caso contrário, usa o diretório
    de dados da plataforma.
    """
    return allowlist_path_for(None)


def allowlist_path_for(data_dir: Path | None = None) -> Path:
    """Caminho do arquivo de destinos autorizados para um diretório de dados.

    A variável de ambiente ``DESKGUARD_ALLOWED_TARGETS_FILE`` tem precedência
    sobre tudo, o que permite isolar a lista em testes e em ambientes
    controlados. Sem ela, o arquivo fica ao lado do banco de dados da
    plataforma.
    """
    override = os.environ.get(ENV_ALLOWLIST_PATH)
    if override:
        return Path(override).expanduser()

    if data_dir is not None:
        return Path(data_dir) / ALLOWLIST_FILENAME

    from deskguard.config import Settings

    return Settings.from_env().data_dir / ALLOWLIST_FILENAME


def load_allowlist(path: Path | None = None) -> TargetAllowlist:
    """Lê a lista de destinos autorizados do disco.

    Um arquivo ausente resulta em lista vazia — e lista vazia significa
    **nenhuma sondagem externa autorizada**. Um arquivo inválido também
    resulta em lista vazia, mas com o motivo registrado em ``warnings``.
    """
    resolved = Path(path) if path is not None else default_allowlist_path()

    if not resolved.exists():
        return TargetAllowlist(path=resolved, available=False)

    try:
        raw = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return TargetAllowlist(
            path=resolved,
            available=False,
            warnings=(f"Não foi possível ler a lista de destinos: {exc}",),
        )

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        return TargetAllowlist(
            path=resolved,
            available=False,
            warnings=(f"Arquivo de destinos inválido (JSON): {exc.msg}.",),
        )

    entries, warnings = _extract_entries(document)
    targets: list[AllowedTarget] = []
    for entry in entries:
        try:
            targets.append(_build_target(entry))
        except AllowlistError as exc:
            warnings.append(str(exc))

    if len(targets) > MAX_TARGETS:
        warnings.append(
            f"A lista tem {len(targets)} destinos; apenas os {MAX_TARGETS} primeiros "
            "serão considerados."
        )
        targets = targets[:MAX_TARGETS]

    return TargetAllowlist(
        targets=tuple(targets),
        path=resolved,
        available=True,
        warnings=tuple(warnings),
    )


def _extract_entries(document: Any) -> tuple[list[Any], list[str]]:
    warnings: list[str] = []
    if isinstance(document, list):
        return list(document), warnings
    if isinstance(document, dict):
        entries = document.get("targets", [])
        if isinstance(entries, list):
            return list(entries), warnings
        return [], ["O campo 'targets' do arquivo de destinos não é uma lista."]
    return [], ["O arquivo de destinos deve conter uma lista ou um objeto com 'targets'."]


def _build_target(entry: Any) -> AllowedTarget:
    if isinstance(entry, str):
        return _build_target({"host": entry})
    if not isinstance(entry, dict):
        raise AllowlistError("Entrada de destino inválida: esperado um objeto.")

    host = str(entry.get("host", "")).strip().lower()
    if not host:
        raise AllowlistError("Entrada de destino sem o campo 'host'.")
    if not is_valid_host(host):
        raise AllowlistError(f"Destino inválido ou não permitido: '{host}'.")

    raw_ports = entry.get("ports", list(DEFAULT_PORTS))
    if raw_ports is None:
        raw_ports = list(DEFAULT_PORTS)
    if not isinstance(raw_ports, (list, tuple)):
        raise AllowlistError(f"Destino '{host}': a lista de portas deve ser uma lista.")

    ports: list[int] = []
    for port in raw_ports:
        try:
            number = int(port)
        except (TypeError, ValueError) as exc:
            raise AllowlistError(
                f"Destino '{host}': porta inválida '{port}'."
            ) from exc
        if not 1 <= number <= 65535:
            raise AllowlistError(
                f"Destino '{host}': a porta {number} está fora da faixa 1-65535."
            )
        if number not in ports:
            ports.append(number)

    if len(ports) > MAX_PORTS_PER_TARGET:
        raise AllowlistError(
            f"Destino '{host}': no máximo {MAX_PORTS_PER_TARGET} portas por destino."
        )
    if not ports:
        ports = list(DEFAULT_PORTS)

    return AllowedTarget(
        host=host,
        ports=tuple(ports),
        description=str(entry.get("description", "")).strip()[:200],
        ping=bool(entry.get("ping", True)),
    )


def save_allowlist(targets: Iterable[AllowedTarget], path: Path | None = None) -> Path:
    """Grava a lista de destinos autorizados.

    Usado pelo comando ``deskguard targets`` da linha de comando. A escrita é
    atômica: grava em arquivo temporário e substitui o original.
    """
    resolved = Path(path) if path is not None else default_allowlist_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)

    document = {
        "targets": [target.to_dict() for target in targets],
    }
    temporary = resolved.with_suffix(resolved.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(resolved)
    return resolved
