"""Validação de entrada na fronteira da plataforma.

Todo parâmetro recebido da interface passa por aqui antes de chegar a um
procedimento. A validação é *fechada*: chave desconhecida é erro, tipo
incompatível é erro e valores fora dos limites declarados são erro.

Isso reduz a superfície de ataque e evita que um parâmetro malicioso seja
encaminhado para uma camada inferior.
"""

from __future__ import annotations

import re
from typing import Any

from deskguard.domain.spec import ProcedureSpec
from deskguard.errors import InvalidParametersError
from deskguard.security.allowlist import (
    MAX_TARGETS,
    TargetAllowlist,
    is_valid_host,
    load_allowlist,
)

_BOOL_TRUE = {"1", "true", "yes", "on", "sim"}
_BOOL_FALSE = {"0", "false", "no", "off", "nao", "não"}


def validate_params(
    spec: ProcedureSpec,
    raw: dict[str, Any] | None,
    *,
    allowlist: TargetAllowlist | None = None,
) -> dict[str, Any]:
    """Valida e normaliza os parâmetros de um procedimento.

    Retorna apenas as chaves declaradas na especificação, com tipos
    normalizados. Parâmetros desconhecidos são rejeitados.

    O parâmetro ``allowlist`` permite injetar a lista de destinos autorizados
    em testes; quando ausente, ela é lida do disco conforme a configuração da
    plataforma.
    """
    raw = raw or {}
    if not isinstance(raw, dict):
        raise InvalidParametersError("Os parâmetros devem ser um objeto JSON.")

    declared = {param.name: param for param in spec.params}
    unknown = sorted(set(raw) - set(declared))
    if unknown:
        raise InvalidParametersError(
            "Parâmetro(s) não reconhecido(s) para este procedimento: "
            + ", ".join(unknown)
        )

    validated: dict[str, Any] = {}
    for name, param in declared.items():
        if name not in raw or raw[name] is None:
            if param.required:
                raise InvalidParametersError(
                    f"O parâmetro obrigatório '{name}' não foi informado."
                )
            validated[name] = param.default
            continue
        validated[name] = _coerce(param.name, param.type, raw[name], param.choices,
                                  param.min_value, param.max_value,
                                  param.pattern, param.max_length,
                                  allowlist=allowlist)
    return validated


def _coerce(
    name: str,
    kind: str,
    value: Any,
    choices: tuple[str, ...],
    min_value: int | None,
    max_value: int | None,
    pattern: str | None,
    max_length: int,
    *,
    allowlist: TargetAllowlist | None = None,
) -> Any:
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in _BOOL_TRUE:
            return True
        if text in _BOOL_FALSE:
            return False
        raise InvalidParametersError(
            f"O parâmetro '{name}' deve ser booleano (recebido: {value!r})."
        )

    if kind == "host_list":
        return _coerce_host_list(name, value, allowlist=allowlist)

    if kind == "integer":
        if isinstance(value, bool):
            raise InvalidParametersError(
                f"O parâmetro '{name}' deve ser um número inteiro."
            )
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise InvalidParametersError(
                f"O parâmetro '{name}' deve ser um número inteiro (recebido: {value!r})."
            ) from exc
        if min_value is not None and number < min_value:
            raise InvalidParametersError(
                f"O parâmetro '{name}' deve ser maior ou igual a {min_value}."
            )
        if max_value is not None and number > max_value:
            raise InvalidParametersError(
                f"O parâmetro '{name}' deve ser menor ou igual a {max_value}."
            )
        return number

    text = str(value).strip()
    if len(text) > max_length:
        raise InvalidParametersError(
            f"O parâmetro '{name}' excede o limite de {max_length} caracteres."
        )
    if kind == "enum":
        if text not in choices:
            raise InvalidParametersError(
                f"O parâmetro '{name}' deve ser um destes valores: {', '.join(choices)}."
            )
        return text
    if pattern and not re.fullmatch(pattern, text):
        raise InvalidParametersError(
            f"O parâmetro '{name}' não corresponde ao formato aceito."
        )
    return text


def _coerce_host_list(
    name: str,
    value: Any,
    *,
    allowlist: TargetAllowlist | None,
) -> list[str]:
    """Valida uma lista de destinos de rede.

    Cada destino precisa ser sintaticamente válido **e** constar da lista de
    destinos autorizados. Esta é a barreira que impede o uso da plataforma
    como sonda para redes arbitrárias.
    """
    if isinstance(value, str):
        items = [part for part in re.split(r"[,;\s]+", value) if part]
    elif isinstance(value, (list, tuple)):
        items = [str(part).strip() for part in value if str(part).strip()]
    else:
        raise InvalidParametersError(
            f"O parâmetro '{name}' deve ser uma lista de destinos de rede."
        )

    if len(items) > MAX_TARGETS:
        raise InvalidParametersError(
            f"O parâmetro '{name}' aceita no máximo {MAX_TARGETS} destinos."
        )

    resolved = allowlist if allowlist is not None else load_allowlist()

    hosts: list[str] = []
    for item in items:
        host = item.strip().lower()
        if not is_valid_host(host):
            raise InvalidParametersError(
                f"O destino '{item}' não é um nome de host ou endereço IPv4 válido."
            )
        if not resolved.allows(host):
            authorized = ", ".join(resolved.hosts()) or "nenhum (lista vazia)"
            raise InvalidParametersError(
                f"O destino '{host}' não está na lista de destinos autorizados. "
                f"Autorizados: {authorized}."
            )
        if host not in hosts:
            hosts.append(host)
    return hosts
