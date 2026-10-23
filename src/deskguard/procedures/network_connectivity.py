"""Procedimento ``network.connectivity`` — DNS, ICMP e TCP em destinos autorizados.

Este é o procedimento mais sensível do DeskGuard, porque emite pacotes de
rede. A segurança se apoia em três barreiras independentes:

1. **Camada de validação** (:mod:`deskguard.security.validation`): um destino
   que não esteja na lista de autorizados é recusado com erro 422, e a
   execução nem chega à camada de coleta.
2. **Camada de coleta** (``network_connectivity.ps1``): o script relê a lista
   de autorizados do disco e descarta qualquer destino que não conste nela.
3. **Escopo da lista**: a lista começa vazia e só o operador a preenche; sem
   autorização explícita, apenas ``localhost`` e o gateway padrão do próprio
   endpoint são sondados.
"""

from __future__ import annotations

from typing import Any

from deskguard.catalog.registry import register
from deskguard.collectors.base import Collector, ProbeContext
from deskguard.collectors.demo import build_demo_network_connectivity
from deskguard.collectors.powershell import PowerShellRunner, script_path
from deskguard.domain.enums import Capability, PrivilegeLevel, Severity
from deskguard.domain.results import CheckResult
from deskguard.domain.spec import ParamSpec, ProcedureSpec, StepSpec
from deskguard.errors import CollectorError
from deskguard.procedures.base import Procedure
from deskguard.security.allowlist import TargetAllowlist, load_allowlist

_SCRIPT_NAME = "network_connectivity.ps1"

_TCP_STATE_LABELS = {
    "aberta": "aberta",
    "recusada": "recusada",
    "tempo_esgotado": "sem resposta (tempo esgotado)",
    "sem_resolucao": "não testada (host não resolvido)",
    "erro": "erro durante a conexão",
}


@register
class NetworkConnectivityProcedure(Procedure):
    """Testa DNS, ICMP e TCP apenas em destinos autorizados."""

    spec = ProcedureSpec(
        id="network.connectivity",
        title="Conectividade de rede",
        category="Rede",
        summary=(
            "Testa resolução DNS, resposta ICMP e conexão TCP em destinos "
            "autorizados, além de localhost e do gateway padrão do endpoint."
        ),
        description=(
            "Diagnostica o caminho de conectividade do endpoint: primeiro a "
            "resolução de nomes, depois o alcance do destino e, por fim, a "
            "abertura das portas autorizadas. A lista de destinos é controlada "
            "pelo operador: sem autorização explícita, apenas o loopback e o "
            "gateway padrão do próprio endpoint são testados. Todas as "
            "operações são estritamente de leitura."
        ),
        capability=Capability.READ_ONLY,
        privilege=PrivilegeLevel.USER,
        risk_notes=(
            "Nenhuma configuração é alterada.",
            "Emite pacotes ICMP e conexões TCP de saída — os destinos de rede ficam visíveis nos logs do firewall.",
            "Destinos fora da lista de autorizados são recusados antes de qualquer coleta.",
        ),
        prerequisites=(
            "Windows com PowerShell 5.1 ou superior disponível.",
            "Destinos informados devem constar da lista de destinos autorizados.",
        ),
        expected_outcomes=(
            "Todos os destinos resolvem e respondem: nenhuma inconclusividade esperada.",
            "Nome não resolvido: falha confirmada — problema de DNS.",
            "Porta fechada ou sem resposta: falha confirmada no caminho de rede.",
            "ICMP sem resposta com TCP aberto: aviso, pois parte dos dispositivos bloqueia ping.",
        ),
        params=(
            ParamSpec(
                name="targets",
                label="Destinos a testar",
                type="host_list",
                default=(),
                help_text=(
                    "Lista de destinos autorizados a serem testados. Vazio significa "
                    "testar todos os destinos da lista de autorizados. Destinos fora "
                    "da lista são recusados."
                ),
            ),
            ParamSpec(
                name="probe_timeout_s",
                label="Tempo limite por sondagem (s)",
                type="integer",
                default=3,
                min_value=1,
                max_value=10,
                help_text="Limite de tempo aplicado a cada operação de DNS, ICMP e TCP.",
            ),
        ),
        steps=(
            StepSpec(
                id="network.dns",
                title="Resolução DNS",
                description="Resolução de nomes dos destinos autorizados.",
            ),
            StepSpec(
                id="network.icmp",
                title="Alcance ICMP",
                description="Resposta a ping dos destinos autorizados.",
            ),
            StepSpec(
                id="network.tcp",
                title="Portas TCP",
                description="Abertura das portas autorizadas em cada destino.",
            ),
        ),
        version="1.0.0",
        tags=("rede", "dns", "ping", "tcp", "conectividade"),
    )

    def build_collectors(self) -> list[Collector]:
        return [
            Collector(
                check_id="network.connectivity",
                title="Conectividade via PowerShell",
                description=(
                    "Resolve nomes, testa ICMP e abre conexões TCP somente em "
                    "destinos autorizados."
                ),
                fn=self._collect_connectivity,
            )
        ]

    def build_demo_collectors(self) -> list[Collector]:
        return build_demo_network_connectivity()

    # ------------------------------------------------------------------
    # Coleta
    # ------------------------------------------------------------------
    def _collect_connectivity(self, ctx: ProbeContext) -> list[CheckResult]:
        allowlist = self._allowlist(ctx)
        requested = [str(item) for item in (ctx.param("targets") or [])]
        targets = self._effective_targets(allowlist, requested)
        timeout_s = int(ctx.param("probe_timeout_s", 3) or 3)

        payload = {
            "allowlist_path": str(allowlist.path) if allowlist.path else "",
            "targets": targets,
            "timeout_ms": timeout_s * 1000,
        }

        runner = PowerShellRunner()
        try:
            outcome = runner.run_script(
                script_path(_SCRIPT_NAME), payload, timeout_s=ctx.timeout_s
            )
        except CollectorError as exc:
            return self._all_inconclusive(
                "Não foi possível executar as sondagens de conectividade.",
                error_code="POWERSHELL_UNAVAILABLE",
                evidence={"detail": str(exc)[:400]},
            )

        if not outcome.ok:
            return self._all_inconclusive(
                "As sondagens de conectividade não produziram dados utilizáveis.",
                error_code="POWERSHELL_FAILED",
                evidence={
                    "stderr": outcome.stderr.strip()[:400],
                    "returncode": outcome.returncode,
                },
            )

        data: dict[str, Any] = outcome.payload
        return [
            self._dns(data, outcome.duration_ms),
            self._icmp(data, outcome.duration_ms),
            self._tcp(data, outcome.duration_ms),
        ]

    def _all_inconclusive(
        self, message: str, error_code: str, evidence: dict[str, Any]
    ) -> list[CheckResult]:
        return [
            CheckResult.inconclusive(
                step.id,
                step.title,
                message,
                error_code=error_code,
                evidence=evidence,
            )
            for step in self.spec.steps
        ]

    def _allowlist(self, ctx: ProbeContext) -> TargetAllowlist:
        shared = ctx.shared.get("allowlist") if ctx.shared else None
        if isinstance(shared, TargetAllowlist):
            return shared
        return load_allowlist()

    def _effective_targets(
        self, allowlist: TargetAllowlist, requested: list[str]
    ) -> list[dict[str, Any]]:
        """Monta a lista de destinos enviada ao script.

        Quando o operador não especifica destinos, todos os destinos
        autorizados são testados. A lista enviada é apenas uma *solicitação*:
        o script revalida cada entrada contra o arquivo de autorizados.
        """
        hosts = requested or list(allowlist.hosts())
        targets: list[dict[str, Any]] = []
        for host in hosts:
            allowed = allowlist.find(host)
            targets.append(
                {
                    "host": host,
                    "ports": list(allowed.ports) if allowed else [],
                    "ping": allowed.ping if allowed else True,
                    "description": allowed.description if allowed else "",
                }
            )
        return targets

    # ------------------------------------------------------------------
    # Interpretação
    # ------------------------------------------------------------------
    def _targets(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        targets = data.get("targets")
        return [item for item in (targets or []) if isinstance(item, dict)]

    def _dns(self, data: dict[str, Any], duration_ms: int) -> CheckResult:
        targets = self._targets(data)
        if not targets:
            return CheckResult.not_applicable(
                "network.dns",
                "Resolução DNS",
                "Nenhum destino foi testado: não há destinos autorizados configurados.",
                evidence=self._context(data),
            )

        falhas = [
            target
            for target in targets
            if not bool((target.get("dns") or {}).get("resolved"))
        ]
        evidence = {
            "context": self._context(data),
            "results": [
                {
                    "host": target.get("host"),
                    "source": target.get("source"),
                    "resolved": (target.get("dns") or {}).get("resolved"),
                    "addresses": (target.get("dns") or {}).get("addresses"),
                    "error": (target.get("dns") or {}).get("error"),
                }
                for target in targets
            ],
        }

        if falhas:
            nomes = ", ".join(str(target.get("host")) for target in falhas)
            return CheckResult.fail(
                "network.dns",
                "Resolução DNS",
                f"Falha de resolução DNS em {len(falhas)} destino(s): {nomes}.",
                severity=Severity.HIGH,
                evidence=evidence,
                remediation=(
                    "Verificar a configuração dos servidores DNS da interface, o "
                    "status do serviço DNS Client e o sufixo de pesquisa."
                ),
                duration_ms=duration_ms,
            )

        return CheckResult.ok(
            "network.dns",
            "Resolução DNS",
            f"{len(targets)} destino(s) resolvido(s) corretamente.",
            evidence=evidence,
            duration_ms=duration_ms,
        )

    def _icmp(self, data: dict[str, Any], duration_ms: int) -> CheckResult:
        targets = self._targets(data)
        if not targets:
            return CheckResult.not_applicable(
                "network.icmp",
                "Alcance ICMP",
                "Nenhum destino foi testado: não há destinos autorizados configurados.",
                evidence=self._context(data),
            )

        testados = [t for t in targets if bool((t.get("icmp") or {}).get("attempted"))]
        if not testados:
            return CheckResult.inconclusive(
                "network.icmp",
                "Alcance ICMP",
                "O teste ICMP não pôde ser executado em nenhum destino.",
                error_code="ICMP_NOT_ATTEMPTED",
                evidence={"context": self._context(data)},
                duration_ms=duration_ms,
            )

        sem_resposta = [
            target
            for target in testados
            if not bool((target.get("icmp") or {}).get("reachable"))
        ]
        evidence = {
            "context": self._context(data),
            "results": [
                {
                    "host": target.get("host"),
                    "source": target.get("source"),
                    "reachable": (target.get("icmp") or {}).get("reachable"),
                    "status": (target.get("icmp") or {}).get("status"),
                    "rtt_ms": (target.get("icmp") or {}).get("rtt_ms"),
                    "error": (target.get("icmp") or {}).get("error"),
                }
                for target in testados
            ],
        }

        if sem_resposta:
            nomes = ", ".join(str(target.get("host")) for target in sem_resposta)
            return CheckResult.warning(
                "network.icmp",
                "Alcance ICMP",
                (
                    f"{len(sem_resposta)} de {len(testados)} destino(s) não responderam "
                    f"ao ICMP: {nomes}. Parte dos dispositivos e regras de firewall "
                    "bloqueia ping — considere o teste de TCP."
                ),
                severity=Severity.LOW,
                evidence=evidence,
                duration_ms=duration_ms,
            )

        return CheckResult.ok(
            "network.icmp",
            "Alcance ICMP",
            f"{len(testados)} destino(s) responderam ao ICMP.",
            evidence=evidence,
            duration_ms=duration_ms,
        )

    def _tcp(self, data: dict[str, Any], duration_ms: int) -> CheckResult:
        targets = self._targets(data)
        testados = [t for t in targets if t.get("tcp")]
        if not testados:
            return CheckResult.not_applicable(
                "network.tcp",
                "Portas TCP",
                (
                    "Nenhuma porta foi testada: os destinos configurados não "
                    "definem portas autorizadas."
                ),
                evidence=self._context(data),
            )

        falhas: list[dict[str, Any]] = []
        for target in testados:
            for porta in target.get("tcp") or []:
                estado = str(porta.get("state"))
                if estado != "aberta":
                    falhas.append(
                        {
                            "host": target.get("host"),
                            "port": porta.get("port"),
                            "state": estado,
                            "error": porta.get("error"),
                        }
                    )

        evidence = {
            "context": self._context(data),
            "results": [
                {
                    "host": target.get("host"),
                    "source": target.get("source"),
                    "ports": [
                        {
                            "port": porta.get("port"),
                            "state": porta.get("state"),
                            "label": _TCP_STATE_LABELS.get(
                                str(porta.get("state")), str(porta.get("state"))
                            ),
                            "error": porta.get("error"),
                        }
                        for porta in target.get("tcp") or []
                    ],
                }
                for target in testados
            ],
        }

        if falhas:
            detalhe = "; ".join(
                f"{item['host']}:{item['port']} ({_TCP_STATE_LABELS.get(str(item['state']), item['state'])})"
                for item in falhas
            )
            return CheckResult.fail(
                "network.tcp",
                "Portas TCP",
                f"{len(falhas)} conexão(ões) não foram estabelecidas: {detalhe}.",
                severity=Severity.MEDIUM,
                evidence=evidence,
                remediation=(
                    "Verificar se o serviço está em execução no destino, se a porta "
                    "está liberada no firewall e se há rota para a rede do destino."
                ),
                duration_ms=duration_ms,
            )

        return CheckResult.ok(
            "network.tcp",
            "Portas TCP",
            f"Todas as {sum(len(t.get('tcp') or []) for t in testados)} porta(s) testada(s) aceitaram conexão.",
            evidence=evidence,
            duration_ms=duration_ms,
        )

    def _context(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "allowlist": data.get("allowlist") or {},
            "gateways": data.get("gateways") or [],
            "rejected_targets": data.get("rejected_targets") or [],
            "timeout_ms": data.get("timeout_ms"),
        }
