"""Contrato base dos procedimentos do catálogo.

Um procedimento é uma unidade de trabalho verificável: recebe um contexto de
execução e devolve uma lista de ``CheckResult``. Não decide o que fazer com o
resultado — essa responsabilidade é do serviço de execução e do gerador de
relatório.
"""

from __future__ import annotations

from typing import Sequence

from deskguard.collectors.base import Collector, ProbeContext, run_collectors
from deskguard.domain.enums import ExecutionMode
from deskguard.domain.results import CheckResult
from deskguard.domain.spec import ProcedureSpec


class Procedure:
    """Base de todos os procedimentos catalogados."""

    spec: ProcedureSpec

    def __init__(self, collectors: Sequence[Collector] | None = None) -> None:
        self._collectors: list[Collector] = (
            list(collectors) if collectors is not None else self.build_collectors()
        )

    def build_collectors(self) -> list[Collector]:
        """Constrói a lista de coletores do procedimento.

        Subclasses implementam este método. A lista pode ser substituída em
        testes por implementações simuladas, o que permite validar o fluxo
        completo sem tocar no sistema do operador.
        """
        raise NotImplementedError

    def build_demo_collectors(self) -> list[Collector] | None:
        """Coletores usados no modo demonstração.

        Quando ``None`` (padrão), o procedimento não pode ser executado em modo
        demonstração e a API recusa a execução.
        """
        return None

    def for_mode(self, mode: ExecutionMode) -> "Procedure":
        """Devolve a instância adequada ao modo de execução solicitado."""
        if mode is ExecutionMode.DEMO:
            demo = self.build_demo_collectors()
            if demo is None:
                raise NotImplementedError(
                    f"O procedimento '{self.spec.id}' não possui modo demonstração."
                )
            return type(self)(demo)
        return self

    @property
    def collectors(self) -> list[Collector]:
        return list(self._collectors)

    def run(self, ctx: ProbeContext) -> list[CheckResult]:
        """Executa as verificações na ordem declarada."""
        return run_collectors(self._collectors, ctx)
