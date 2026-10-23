"""Interpretação do estado dos serviços do Windows para o vocabulário do DeskGuard.

O Windows descreve cada serviço por dois campos independentes:

* **Status** — o que está acontecendo agora (``Running``, ``Stopped``,
  ``Paused``, ``Pending``);
* **StartType** — o que deve acontecer no próximo reinício (``Automatic``,
  ``Manual``, ``Disabled``).

É a *combinação* dos dois que diz se existe um problema. Um serviço ``Stopped``
com ``StartType = Manual`` é normal em vários casos: serviços que disparam por
evento, como o Windows Update e o BITS, ficam parados entre uma execução e
outra. O mesmo serviço parado com ``StartType = Automatic`` é um desvio
confirmado — ele deveria ter subido sozinho.

Por isso a classificação usa um **perfil** por serviço, que declara a
criticidade, o impacto no atendimento, o tipo de inicialização esperado e se o
serviço pode estar parado em uma operação normal. O texto cru do status nunca
é interpretado sozinho.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from deskguard.domain.enums import CheckStatus, Severity

_RUNNING = "Running"
_STOPPED = "Stopped"
_PAUSED = "Paused"
_PENDING = "Pending"
_UNKNOWN = "Unknown"

_AUTOMATIC = "Automatic"
_AUTOMATIC_DELAYED = "AutomaticDelayedStart"
_MANUAL = "Manual"
_DISABLED = "Disabled"


def _menor(a: Severity, b: Severity) -> Severity:
    """Devolve a severidade mais baixa entre duas."""
    return a if a.rank <= b.rank else b


@dataclass(frozen=True, slots=True)
class ServiceProfile:
    """Descrição do comportamento esperado de um serviço monitorado."""

    key: str
    label: str
    severity: Severity
    impact: str
    remediation: str
    expected_start_types: tuple[str, ...] = ()
    normal_stopped: bool = False
    """Verdadeiro quando o serviço pode estar parado em uma operação normal.

    Serviços de disparo por evento (inicialização manual) ficam parados entre
    uma execução e outra; tratá-los como falha produziria falso positivo.
    """


@dataclass(frozen=True, slots=True)
class ServiceState:
    """Estado interpretado de um serviço."""

    name: str
    label: str
    status: CheckStatus
    severity: Severity
    message: str
    state: str
    start_type: str
    impact: str = ""
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "status": str(self.status),
            "severity": str(self.severity),
            "message": self.message,
            "state": self.state,
            "start_type": self.start_type,
            "impact": self.impact,
            "error_code": self.error_code,
        }


# --------------------------------------------------------------------------
# Perfis dos serviços monitorados
# --------------------------------------------------------------------------
SERVICE_PROFILES: dict[str, ServiceProfile] = {
    "spooler": ServiceProfile(
        key="Spooler",
        label="Fila de impressão (Print Spooler)",
        severity=Severity.HIGH,
        impact=(
            "Sem o Spooler nenhum trabalho chega à impressora: a fila para e o "
            "erro típico é 'nenhuma impressora instalada' ou 'erro de impressão'."
        ),
        remediation=(
            "Verificar o tipo de inicialização do serviço Print Spooler e se o "
            "processo spoolsv.exe foi encerrado; restaurar a inicialização automática."
        ),
        expected_start_types=(_AUTOMATIC,),
    ),
    "dnscache": ServiceProfile(
        key="Dnscache",
        label="Cliente DNS",
        severity=Severity.HIGH,
        impact=(
            "Sem o cliente DNS o endpoint não resolve nomes: intranet, e-mail e "
            "portais ficam inacessíveis mesmo com o cabo de rede conectado."
        ),
        remediation=(
            "Verificar o serviço Cliente DNS e as políticas que podem impedi-lo "
            "de iniciar; reiniciar o serviço após a revisão."
        ),
        expected_start_types=(_AUTOMATIC,),
    ),
    "dhcp": ServiceProfile(
        key="DHCP",
        label="Cliente DHCP",
        severity=Severity.MEDIUM,
        impact=(
            "Sem o cliente DHCP o endpoint não obtém endereço IP, máscara e "
            "gateway automaticamente. Em redes de endereçamento estático a "
            "parada é esperada."
        ),
        remediation=(
            "Confirmar se o endpoint usa endereço estático; se usa DHCP, "
            "reiniciar o serviço Cliente DHCP e o adaptador de rede."
        ),
        expected_start_types=(_AUTOMATIC,),
    ),
    "wlansvc": ServiceProfile(
        key="WlanSvc",
        label="Rede sem fio (WLAN AutoConfig)",
        severity=Severity.HIGH,
        impact=(
            "Sem o serviço WLAN o computador não conecta a redes sem fio — o "
            "sintoma típico é o Wi-Fi ausente da lista de redes disponíveis."
        ),
        remediation=(
            "Verificar o tipo de inicialização do serviço WLAN AutoConfig e o "
            "estado do adaptador sem fio nas Configurações de rede."
        ),
        expected_start_types=(_AUTOMATIC,),
    ),
    "wuauserv": ServiceProfile(
        key="wuauserv",
        label="Windows Update",
        severity=Severity.LOW,
        impact=(
            "Com o Windows Update desativado o endpoint deixa de receber "
            "correções de segurança. O desativamento é comum como política "
            "corporativa e precisa ser confirmado antes de ser tratado como falha."
        ),
        remediation=(
            "Confirmar com o cliente se o Windows Update é bloqueado por "
            "política corporativa; caso contrário, restaurar a inicialização "
            "manual com disparo por evento."
        ),
        expected_start_types=(_MANUAL,),
        normal_stopped=True,
    ),
    "bits": ServiceProfile(
        key="BITS",
        label="Transferências em segundo plano (BITS)",
        severity=Severity.LOW,
        impact=(
            "Sem BITS as atualizações e outras transferências em segundo plano "
            "podem reiniciar do zero a cada interrupção de rede."
        ),
        remediation=(
            "Verificar as políticas que restringem o BITS e o espaço livre em "
            "disco, que é o destino típico de interrupção dessa transferência."
        ),
        expected_start_types=(_MANUAL,),
        normal_stopped=True,
    ),
    "winmgmt": ServiceProfile(
        key="winmgmt",
        label="Instrumentação de gerenciamento (WMI)",
        severity=Severity.MEDIUM,
        impact=(
            "Sem WMI não há inventário de hardware nem coleta de desempenho: o "
            "DeskGuard e boa parte das ferramentas de suporte param de coletar dados."
        ),
        remediation=(
            "Verificar o serviço Instrumentação de Gerenciamento do Windows e "
            "as permissões do repositório WMI."
        ),
        expected_start_types=(_AUTOMATIC,),
    ),
    "rpcss": ServiceProfile(
        key="RpcSs",
        label="Chamada remota de procedimento (RPC)",
        severity=Severity.HIGH,
        impact=(
            "Sem RPC o Windows não sobe serviços dependentes dele; o logon do "
            "usuário pode não concluir e o endpoint fica instável."
        ),
        remediation=(
            "Verificar o serviço Chamada Remota de Procedimento (RPC) e o "
            "estado da inicialização do sistema."
        ),
        expected_start_types=(_AUTOMATIC,),
    ),
    "dcomlaunch": ServiceProfile(
        key="DcomLaunch",
        label="Inicializador de processos DCOM",
        severity=Severity.HIGH,
        impact=(
            "Sem o inicializador DCOM vários serviços não sobem; o endpoint "
            "fica instável e com falhas em cascata."
        ),
        remediation=(
            "Verificar o serviço DCOM Server Process Launcher e o log de "
            "inicialização do sistema."
        ),
        expected_start_types=(_AUTOMATIC,),
    ),
    "dps": ServiceProfile(
        key="DPS",
        label="Política de diagnóstico",
        severity=Severity.LOW,
        impact=(
            "Com a política de diagnóstico parada o Windows não executa a "
            "coleta de dados de diagnóstico após erros de energia ou do sistema."
        ),
        remediation=(
            "Verificar a política de diagnóstico; o estado normal é em execução "
            "com inicialização automática ou por evento."
        ),
        expected_start_types=(_AUTOMATIC, _MANUAL),
        normal_stopped=True,
    ),
}


def profile_for(name: str) -> ServiceProfile | None:
    """Devolve o perfil do serviço, se ele for monitorado."""
    return SERVICE_PROFILES.get(normalize_service_name(name))


def normalize_service_name(name: str) -> str:
    """Normaliza o nome de um serviço para comparação.

    O Windows devolve o nome do mesmo serviço com grafias diferentes
    (``RPCSS``, ``rpcss``, ``RpcSs``) e, em alguns casos, anexa um alias de
    grupo de serviços (``RPCSS,http``). A comparação é feita sempre sobre a
    primeira parte, em minúsculas.
    """
    text = str(name or "").strip()
    if not text:
        return ""
    return text.split(",", 1)[0].strip().lower()


def _base(
    service: dict[str, Any], profile: ServiceProfile | None
) -> tuple[str, str, str, str, bool, ServiceProfile | None]:
    """Extrai os campos relevantes e resolve o perfil do serviço.

    Quando nenhum perfil é informado, o perfil canônico do serviço é
    procurado pelo nome: assim a interpretação não depende de quem chamou.
    """
    name = str(service.get("name") or "").strip() or "(desconhecido)"
    resolved = profile if profile is not None else profile_for(name)
    label = resolved.label if resolved else name
    state = str(service.get("status") or _UNKNOWN).strip() or _UNKNOWN
    start_type = str(service.get("start_type") or _UNKNOWN).strip() or _UNKNOWN
    found = bool(service.get("found", True))
    return name, label, state, start_type, found, resolved


def classify_service(
    service: dict[str, Any], profile: ServiceProfile | None = None
) -> ServiceState:
    """Interpreta o estado atual de um serviço.

    O resultado distingue três situações que o texto bruto não distingue:

    * serviço parado que deveria estar em execução (falha confirmada);
    * serviço parado por desenho (inicialização manual com disparo por evento);
    * serviço em estado transitório ou desconhecido (inconclusivo).
    """
    name, label, state, start_type, found, resolved = _base(service, profile)
    severity = resolved.severity if resolved else Severity.LOW
    impact = resolved.impact if resolved else ""

    if not found:
        return ServiceState(
            name=name,
            label=label,
            status=CheckStatus.NOT_APPLICABLE,
            severity=Severity.INFO,
            message=f"O serviço '{label}' não existe neste endpoint.",
            state=state,
            start_type=start_type,
            impact=impact,
            error_code="SERVICE_NOT_FOUND",
        )

    if state == _UNKNOWN:
        return ServiceState(
            name=name,
            label=label,
            status=CheckStatus.INCONCLUSIVE,
            severity=Severity.INFO,
            message="O Windows não informou o estado deste serviço.",
            state=state,
            start_type=start_type,
            impact=impact,
            error_code="SERVICE_STATE_UNKNOWN",
        )

    if state == _PENDING:
        return ServiceState(
            name=name,
            label=label,
            status=CheckStatus.INCONCLUSIVE,
            severity=Severity.INFO,
            message=(
                "O serviço está em estado transitório (iniciando ou "
                "parando); colete novamente em alguns instantes."
            ),
            state=state,
            start_type=start_type,
            impact=impact,
            error_code="SERVICE_STATE_PENDING",
        )

    if state == _PAUSED:
        status = CheckStatus.FAIL if severity.rank >= Severity.HIGH.rank else CheckStatus.WARN
        return ServiceState(
            name=name,
            label=label,
            status=status,
            severity=severity if status is CheckStatus.FAIL else _menor(severity, Severity.LOW),
            message=f"O serviço '{label}' está pausado.",
            state=state,
            start_type=start_type,
            impact=impact,
        )

    if state == _RUNNING:
        if start_type == _DISABLED:
            return ServiceState(
                name=name,
                label=label,
                status=CheckStatus.WARN,
                severity=_menor(severity, Severity.MEDIUM),
                message=(
                    f"O serviço '{label}' está em execução, mas configurado como "
                    "desativado: não voltará a subir após o próximo reinício."
                ),
                state=state,
                start_type=start_type,
                impact=impact,
            )
        return ServiceState(
            name=name,
            label=label,
            status=CheckStatus.PASS,
            severity=Severity.INFO,
            message=f"O serviço '{label}' está em execução.",
            state=state,
            start_type=start_type,
            impact=impact,
        )

    # A partir daqui o serviço está parado.
    if start_type == _DISABLED:
        status = CheckStatus.FAIL if severity.rank >= Severity.HIGH.rank else CheckStatus.WARN
        return ServiceState(
            name=name,
            label=label,
            status=status,
            severity=severity if status is CheckStatus.FAIL else _menor(severity, Severity.LOW),
            message=(
                f"O serviço '{label}' está desativado e parado."
            ),
            state=state,
            start_type=start_type,
            impact=impact,
        )

    if start_type in (_AUTOMATIC, _AUTOMATIC_DELAYED):
        return ServiceState(
            name=name,
            label=label,
            status=CheckStatus.FAIL,
            severity=severity,
            message=(
                f"O serviço '{label}' está parado, mas configurado para iniciar "
                "automaticamente: desvio confirmado."
            ),
            state=state,
            start_type=start_type,
            impact=impact,
        )

    if start_type == _MANUAL:
        if resolved is not None and resolved.normal_stopped:
            return ServiceState(
                name=name,
                label=label,
                status=CheckStatus.PASS,
                severity=Severity.INFO,
                message=(
                    f"O serviço '{label}' está parado, o que é esperado para um "
                    "serviço de inicialização manual (dispara por evento)."
                ),
                state=state,
                start_type=start_type,
                impact=impact,
            )
        return ServiceState(
            name=name,
            label=label,
            status=CheckStatus.WARN,
            severity=Severity.LOW,
            message=(
                f"O serviço '{label}' está parado e configurado como manual; "
                "confirme se deveria estar em execução."
            ),
            state=state,
            start_type=start_type,
            impact=impact,
        )

    return ServiceState(
        name=name,
        label=label,
        status=CheckStatus.INCONCLUSIVE,
        severity=Severity.INFO,
        message=(
            f"O serviço '{label}' está parado, mas o Windows não informou o "
            "tipo de inicialização."
        ),
        state=state,
        start_type=start_type,
        impact=impact,
        error_code="SERVICE_START_TYPE_UNKNOWN",
    )


def classify_startup(
    service: dict[str, Any], profile: ServiceProfile | None = None
) -> ServiceState:
    """Interpreta o tipo de inicialização de um serviço.

    O tipo de inicialização é o que decide se o serviço volta a funcionar
    depois de um reinício: um serviço crítico parado com inicialização
    automática é falha confirmada, e um serviço desativado é um desvio
    permanente, mesmo que esteja em execução agora.
    """
    name, label, state, start_type, found, resolved = _base(service, profile)
    severity = resolved.severity if resolved else Severity.LOW
    impact = resolved.impact if resolved else ""

    if not found:
        return ServiceState(
            name=name,
            label=label,
            status=CheckStatus.NOT_APPLICABLE,
            severity=Severity.INFO,
            message=f"O serviço '{label}' não existe neste endpoint.",
            state=state,
            start_type=start_type,
            impact=impact,
            error_code="SERVICE_NOT_FOUND",
        )

    if start_type == _UNKNOWN:
        return ServiceState(
            name=name,
            label=label,
            status=CheckStatus.INCONCLUSIVE,
            severity=Severity.INFO,
            message="O Windows não informou o tipo de inicialização do serviço.",
            state=state,
            start_type=start_type,
            impact=impact,
            error_code="SERVICE_START_TYPE_UNKNOWN",
        )

    if start_type == _DISABLED:
        status = CheckStatus.FAIL if severity.rank >= Severity.HIGH.rank else CheckStatus.WARN
        return ServiceState(
            name=name,
            label=label,
            status=status,
            severity=severity if status is CheckStatus.FAIL else _menor(severity, Severity.LOW),
            message=(
                f"O serviço '{label}' está configurado como desativado e não "
                "iniciará no próximo reinício."
            ),
            state=state,
            start_type=start_type,
            impact=impact,
        )

    expected = resolved.expected_start_types if resolved else ()
    if expected and start_type not in expected:
        return ServiceState(
            name=name,
            label=label,
            status=CheckStatus.WARN,
            severity=Severity.LOW,
            message=(
                f"O serviço '{label}' está configurado como '{start_type}'; o "
                f"padrão do Windows para este serviço é "
                f"{' ou '.join(expected)}."
            ),
            state=state,
            start_type=start_type,
            impact=impact,
        )

    return ServiceState(
        name=name,
        label=label,
        status=CheckStatus.PASS,
        severity=Severity.INFO,
        message=(
            f"O serviço '{label}' está configurado como '{start_type}', "
            "conforme o padrão do Windows."
        ),
        state=state,
        start_type=start_type,
        impact=impact,
    )
