"""Interpretação da coleta de segurança do Windows para o vocabulário do DeskGuard.

Este módulo traduz as evidências brutas do endpoint em *achados* classificados,
com severidade, impacto, recomendação e referência documentada. Ele não
executa nada: apenas lê o dicionário devolvido por ``security_audit.ps1`` e
decide o que é um desvio confirmado, o que é apenas uma informação e o que
não pôde ser verificado.

Três princípios guideiam a classificação:

1. **Não inventar falha.** Uma verificação que não pôde ser executada é
   *inconclusiva*, nunca uma falha. Vários componentes de segurança do Windows
   exigem elevação de privilégio ou um serviço ativo que pode não existir em
   toda máquina.
2. **Não confundir estado desconhecido com estado ruim.** O campo
   ``productState`` do SecurityCenter2 codifica vários atributos em um número
   hexadecimal; a documentação pública é ambígua para parte dos bits. Por isso
   apenas os bits amplamente documentados são interpretados e o valor bruto é
   preservado na evidência.
3. **Justificar sempre.** Todo desvio confirmado traz impacto (o que acontece
   se nada for feito) e recomendação (o que fazer), com uma referência para
   que a afirmação possa ser conferida.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from deskguard.domain.enums import CheckStatus, Severity

_HEX_PATTERN = re.compile(r"[0-9A-Fa-f]{6}")

SEVERITY_LABELS: dict[Severity, str] = {
    Severity.INFO: "Informativa",
    Severity.LOW: "Baixa",
    Severity.MEDIUM: "Média",
    Severity.HIGH: "Alta",
    Severity.CRITICAL: "Crítica",
}

PROFILE_LABELS: dict[str, str] = {
    "domain": "Domínio",
    "private": "Privado",
    "public": "Público",
}

FULL_SCAN_MAX_AGE_DAYS = 30
"""Prazo considera aceitável para uma varredura completa do antivírus."""

SCREEN_LOCK_MAX_TIMEOUT_SECONDS = 900
"""Tempo de bloqueio de tela aceito antes de virar achado (15 minutos)."""


@dataclass(frozen=True, slots=True)
class SecurityFinding:
    """Achado de segurança interpretado a partir de uma evidência coletada."""

    key: str
    label: str
    status: CheckStatus
    severity: Severity
    message: str
    impact: str = ""
    remediation: str = ""
    reference: str = ""
    error_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def severity_label(self) -> str:
        return SEVERITY_LABELS.get(self.severity, str(self.severity))

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": str(self.status),
            "severity": str(self.severity),
            "severity_label": self.severity_label,
            "message": self.message,
            "impact": self.impact,
            "remediation": self.remediation,
            "reference": self.reference,
            "error_code": self.error_code,
            "details": self.details,
        }


def _profile_label(name: str) -> str:
    """Devolve o rótulo legível do perfil de firewall."""
    return PROFILE_LABELS.get(name.strip().lower(), name or "Perfil")


def _inconclusive(
    key: str,
    label: str,
    message: str,
    *,
    error_code: str,
    details: dict[str, Any] | None = None,
) -> SecurityFinding:
    return SecurityFinding(
        key=key,
        label=label,
        status=CheckStatus.INCONCLUSIVE,
        severity=Severity.INFO,
        message=message,
        error_code=error_code,
        details=details or {},
    )


# --------------------------------------------------------------------------
# Windows Firewall
# --------------------------------------------------------------------------
def classify_firewall(section: dict[str, Any] | None) -> list[SecurityFinding]:
    """Interpreta o estado dos perfis do Windows Firewall."""
    if not section:
        return [
            _inconclusive(
                "firewall.unavailable",
                "Windows Firewall",
                "A coleta não retornou a seção de firewall.",
                error_code="MISSING_SECTION",
            )
        ]

    if not section.get("available"):
        return [
            _inconclusive(
                "firewall.unavailable",
                "Windows Firewall",
                "Não foi possível consultar o estado do firewall neste endpoint.",
                error_code="FIREWALL_UNAVAILABLE",
                details={"error": str(section.get("error", ""))[:400]},
            )
        ]

    perfis = [item for item in (section.get("profiles") or []) if isinstance(item, dict)]
    if not perfis:
        return [
            _inconclusive(
                "firewall.no_profiles",
                "Windows Firewall",
                "A consulta ao firewall não retornou nenhum perfil.",
                error_code="NO_FIREWALL_PROFILES",
                details={"error": str(section.get("error", ""))[:400]},
            )
        ]

    achados: list[SecurityFinding] = []
    for perfil in perfis:
        nome = str(perfil.get("name", "")).strip()
        rotulo = _profile_label(nome)
        estado = str(perfil.get("enabled", "Unknown"))
        detalhes = {
            "profile": nome,
            "enabled": estado,
            "default_inbound_action": perfil.get("default_inbound_action"),
            "default_outbound_action": perfil.get("default_outbound_action"),
        }

        if estado == "True":
            achados.append(
                SecurityFinding(
                    key=f"firewall.{nome.lower() or 'perfil'}",
                    label=f"Firewall - perfil {rotulo}",
                    status=CheckStatus.PASS,
                    severity=Severity.INFO,
                    message=f"O Windows Firewall está ativo no perfil {rotulo}.",
                    details=detalhes,
                )
            )
        elif estado == "False":
            achados.append(
                SecurityFinding(
                    key=f"firewall.{nome.lower() or 'perfil'}",
                    label=f"Firewall - perfil {rotulo}",
                    status=CheckStatus.FAIL,
                    severity=Severity.CRITICAL,
                    message=f"O Windows Firewall está desativado no perfil {rotulo}.",
                    impact=(
                        "Com o firewall desligado, todo o tráfego de entrada do "
                        f"perfil {rotulo} chega ao endpoint sem filtragem: serviços "
                        "expostos na rede podem ser acessados por terceiros."
                    ),
                    remediation=(
                        f"Reativar o Windows Defender Firewall no perfil {rotulo} "
                        "(painel de segurança do Windows) e revisar as regras de "
                        "entrada permitidas."
                    ),
                    reference=(
                        "Microsoft Learn: defender-firewall-with-advanced-security"
                    ),
                    details=detalhes,
                )
            )
        else:
            achados.append(
                _inconclusive(
                    f"firewall.{nome.lower() or 'perfil'}",
                    f"Firewall - perfil {rotulo}",
                    f"Não foi possível determinar o estado do firewall no perfil {rotulo}.",
                    error_code="FIREWALL_STATE_UNKNOWN",
                    details=detalhes,
                )
            )

    return achados


# --------------------------------------------------------------------------
# Antivírus
# --------------------------------------------------------------------------
def _parse_product_state(bruto: str, hexadecimal: bool = False) -> int | None:
    """Converte o texto de ``productState`` em inteiro.

    O WMI entrega o valor como decimal, mas algumas ferramentas o exibem em
    hexadecimal; a forma hexadecimal de seis dígitos é reconhecida pelo zero
    à esquerda. O valor também é limitado a 24 bits, como o ``uint32`` de
    origem.
    """
    texto = (bruto or "").strip()
    if not texto:
        return None
    hexadecimal_texto = hexadecimal or (
        len(texto) == 6 and texto[0] == "0" and _HEX_PATTERN.fullmatch(texto) is not None
    )
    if hexadecimal_texto:
        try:
            return int(texto, 16)
        except ValueError:
            return None
    try:
        return int(texto)
    except ValueError:
        try:
            return int(texto, 16)
        except ValueError:
            return None


def decode_product_state(
    product_state: str, *, hexadecimal: bool = False
) -> dict[str, Any]:
    """Decodifica o campo ``productState`` do SecurityCenter2.

    O valor é um inteiro de 32 bits que codifica, em bytes, o provedor, o
    estado de proteção e a situação das assinaturas. A documentação pública
    diverge em parte dos bits; por isso a decodificação aqui é
    **conservadora**: só o bit de proteção desativada (``0x10`` no segundo
    byte) e o bit de assinaturas desatualizadas (``0x10`` no terceiro byte)
    são interpretados. Qualquer outra combinação vira ``None`` (desconhecido),
    e o valor bruto é preservado.
    """
    bruto = str(product_state or "").strip()
    resultado: dict[str, Any] = {
        "raw": bruto,
        "enabled": None,
        "out_of_date": None,
        "provider_byte": None,
    }
    valor = _parse_product_state(bruto, hexadecimal)
    if valor is None:
        return resultado

    byte_provedor = valor & 0xFF
    byte_estado = (valor >> 8) & 0xFF
    byte_assinaturas = (valor >> 16) & 0xFF

    # O byte do provedor é preservado como evidência, sem rótulo de fabricante:
    # a documentação pública não é consistente o bastante para atribuí-lo.
    resultado["provider_byte"] = f"0x{byte_provedor:02X}"
    resultado["enabled"] = False if byte_estado == 0x10 else None
    resultado["out_of_date"] = True if byte_assinaturas == 0x10 else None
    resultado["decoded_hex"] = f"0x{valor:06X}"
    return resultado


def _produtos_antivirus(section: dict[str, Any]) -> list[dict[str, Any]]:
    """Normaliza a lista de produtos antivírus registrados."""
    produtos: list[dict[str, Any]] = []
    for item in section.get("products") or []:
        if not isinstance(item, dict):
            continue
        nome = str(item.get("name", "")).strip()
        if not nome:
            continue
        bruto = str(item.get("product_state", ""))
        hex_bruto = str(item.get("product_state_hex", "")).strip()
        decodificado = decode_product_state(hex_bruto or bruto, hexadecimal=bool(hex_bruto))
        produtos.append(
            {
                "name": nome,
                "product_state": bruto,
                "product_state_hex": hex_bruto or decodificado.get("decoded_hex", ""),
                "enabled": decodificado["enabled"],
                "out_of_date": decodificado["out_of_date"],
                "provider_byte": decodificado["provider_byte"],
                "decoded_hex": decodificado.get("decoded_hex", ""),
            }
        )
    return produtos


def classify_antivirus(
    section: dict[str, Any] | None, stale_threshold_days: int = 7
) -> list[SecurityFinding]:
    """Interpreta a proteção antivírus do endpoint."""
    if not section:
        return [
            _inconclusive(
                "av.unavailable",
                "Proteção antivírus",
                "A coleta não retornou a seção de proteção antivírus.",
                error_code="MISSING_SECTION",
            )
        ]

    defender = section.get("defender") if isinstance(section.get("defender"), dict) else {}
    produtos = _produtos_antivirus(section)
    defender_disponivel = bool(defender.get("available"))
    ativos = [item for item in produtos if item["enabled"] is True]
    desativados = [item for item in produtos if item["enabled"] is False]
    indeterminados = [item for item in produtos if item["enabled"] is None]
    desatualizados = [item for item in produtos if item["out_of_date"] is True]

    achados: list[SecurityFinding] = []

    # 1. Existência de proteção ativa.
    if not defender_disponivel and not produtos:
        achados.append(
            SecurityFinding(
                key="av.none",
                label="Proteção antivírus",
                status=CheckStatus.FAIL,
                severity=Severity.HIGH,
                message="Nenhuma proteção antivírus foi encontrada neste endpoint.",
                impact=(
                    "Sem antivírus registrado o endpoint não tem varredura de "
                    "malware, e a remoção de um arquivo infectado deixa de ter "
                    "detecção e quarentena."
                ),
                remediation=(
                    "Instalar ou reativar uma solução de proteção contra "
                    "malware compatível com a política do ambiente."
                ),
                reference="Microsoft Learn: antivirus-and-antimalware-protection",
                details={"products": produtos, "defender_error": defender.get("error", "")},
            )
        )
    elif produtos and not ativos and not indeterminados and not defender_disponivel:
        achados.append(
            SecurityFinding(
                key="av.all_disabled",
                label="Proteção antivírus",
                status=CheckStatus.FAIL,
                severity=Severity.HIGH,
                message=(
                    "Nenhum dos produtos antivírus registrados está com proteção "
                    "ativa: " + ", ".join(item["name"] for item in desativados) + "."
                ),
                impact=(
                    "Os produtos constam do SecurityCenter2, mas estão "
                    "desativados: o endpoint permanece sem varredura de malware."
                ),
                remediation=(
                    "Reativar a proteção em tempo real de um dos produtos "
                    "registrados ou instalar uma solução compatível."
                ),
                reference="Microsoft Learn: securitycenter2-antivirusproduct",
                details={"products": produtos},
            )
        )
    elif ativos:
        achados.append(
            SecurityFinding(
                key="av.active",
                label="Proteção antivírus",
                status=CheckStatus.PASS,
                severity=Severity.INFO,
                message=(
                    "Proteção antivírus ativa: "
                    + ", ".join(item["name"] for item in ativos)
                    + "."
                ),
                details={"products": produtos},
            )
        )
    elif defender_disponivel:
        achados.append(
            SecurityFinding(
                key="av.defender_present",
                label="Proteção antivírus",
                status=CheckStatus.PASS,
                severity=Severity.INFO,
                message="O Microsoft Defender está presente neste endpoint.",
                details={"products": produtos},
            )
        )
    else:
        achados.append(
            _inconclusive(
                "av.state_unknown",
                "Proteção antivírus",
                (
                    "Não foi possível confirmar que algum dos produtos antivírus "
                    "registrados ("
                    + ", ".join(item["name"] for item in produtos)
                    + ") esteja com proteção em tempo real ativa."
                ),
                error_code="AV_STATE_UNKNOWN",
                details={"products": produtos},
            )
        )

    # 2. Proteção em tempo real (informação do Defender).
    if defender_disponivel:
        if defender.get("antivirus_enabled") is False:
            achados.append(
                SecurityFinding(
                    key="av.disabled",
                    label="Proteção em tempo real",
                    status=CheckStatus.FAIL,
                    severity=Severity.HIGH,
                    message="A proteção do Microsoft Defender está desativada.",
                    impact=(
                        "Com a proteção desativada o Defender não examina "
                        "arquivos, downloads ou conexões de rede."
                    ),
                    remediation="Reativar a proteção do Microsoft Defender.",
                    reference="Microsoft Learn: microsoft-defender-antivirus",
                    details={"antivirus_enabled": False},
                )
            )
        if defender.get("realtime_protection") is False:
            achados.append(
                SecurityFinding(
                    key="av.realtime_disabled",
                    label="Proteção em tempo real",
                    status=CheckStatus.FAIL,
                    severity=Severity.HIGH,
                    message="A proteção em tempo real do Defender está desativada.",
                    impact=(
                        "A varredura de arquivos e conexões em tempo real fica "
                        "desligada, e o malware é detectado apenas na varredura "
                        "manual."
                    ),
                    remediation=(
                        "Reativar a proteção em tempo real nas Configurações de "
                        "Windows > Segurança do Windows > Proteção contra vírus."
                    ),
                    reference="Microsoft Learn: microsoft-defender-antivirus",
                    details={"realtime_protection": False},
                )
            )

    # 3. Idade das assinaturas.
    idade_assinaturas = defender.get("signature_age_days")
    if isinstance(idade_assinaturas, int):
        if idade_assinaturas > stale_threshold_days:
            achados.append(
                SecurityFinding(
                    key="av.signatures_stale",
                    label="Assinaturas do antivírus",
                    status=CheckStatus.WARN,
                    severity=Severity.MEDIUM,
                    message=(
                        f"As assinaturas do Defender estão desatualizadas há "
                        f"{idade_assinaturas} dia(s) (limite de "
                        f"{stale_threshold_days})."
                    ),
                    impact=(
                        "Malware publicado nos últimos dias pode não ser "
                        "reconhecido pela varredura do endpoint."
                    ),
                    remediation=(
                        "Forçar a atualização das assinaturas do antivírus ou "
                        "verificar por que a atualização automática não ocorre."
                    ),
                    reference="Microsoft Learn: microsoft-defender-antivirus",
                    details={
                        "signature_age_days": idade_assinaturas,
                        "threshold_days": stale_threshold_days,
                    },
                )
            )
        else:
            achados.append(
                SecurityFinding(
                    key="av.signatures_current",
                    label="Assinaturas do antivírus",
                    status=CheckStatus.PASS,
                    severity=Severity.INFO,
                    message=(
                        f"As assinaturas do Defender estão atualizadas "
                        f"({idade_assinaturas} dia(s))."
                    ),
                    details={"signature_age_days": idade_assinaturas},
                )
            )
    elif desatualizados:
        achados.append(
            SecurityFinding(
                key="av.signatures_stale",
                label="Assinaturas do antivírus",
                status=CheckStatus.WARN,
                severity=Severity.MEDIUM,
                message=(
                    "Produto antivírus com assinaturas desatualizadas: "
                    + ", ".join(item["name"] for item in desatualizados)
                    + "."
                ),
                impact=(
                    "Malware recente pode não ser reconhecido pela varredura "
                    "do endpoint."
                ),
                remediation=(
                    "Verificar a atualização das assinaturas do produto "
                    "antivírus em uso."
                ),
                reference="Microsoft Learn: securitycenter2-antivirusproduct",
                details={"products": desatualizados},
            )
        )
    elif defender_disponivel or produtos:
        achados.append(
            _inconclusive(
                "av.signatures_unknown",
                "Assinaturas do antivírus",
                "A idade das assinaturas do antivírus não pôde ser determinada.",
                error_code="AV_SIGNATURE_AGE_UNKNOWN",
                details={
                    "threshold_days": stale_threshold_days,
                    "defender_error": defender.get("error", ""),
                    "products": produtos,
                },
            )
        )

    # 4. Idade da última varredura.
    idade_quick = defender.get("quick_scan_age_days")
    if isinstance(idade_quick, int):
        if idade_quick > stale_threshold_days:
            achados.append(
                SecurityFinding(
                    key="av.quick_scan_stale",
                    label="Última varredura rápida",
                    status=CheckStatus.WARN,
                    severity=Severity.MEDIUM,
                    message=(
                        f"A varredura rápida do Defender aconteceu há "
                        f"{idade_quick} dia(s) (limite de {stale_threshold_days})."
                    ),
                    impact=(
                        "Malware já presente no endpoint pode não ter sido "
                        "detectado pela varredura rápida recente."
                    ),
                    remediation=(
                        "Executar uma varredura rápida e configurar a varredura "
                        "automática com frequência."
                    ),
                    reference="Microsoft Learn: microsoft-defender-antivirus",
                    details={
                        "quick_scan_age_days": idade_quick,
                        "threshold_days": stale_threshold_days,
                    },
                )
            )
        else:
            achados.append(
                SecurityFinding(
                    key="av.quick_scan_current",
                    label="Última varredura rápida",
                    status=CheckStatus.PASS,
                    severity=Severity.INFO,
                    message=(
                        f"A varredura rápida do Defender foi feita há "
                        f"{idade_quick} dia(s)."
                    ),
                    details={"quick_scan_age_days": idade_quick},
                )
            )
    elif defender_disponivel:
        achados.append(
            _inconclusive(
                "av.quick_scan_unknown",
                "Última varredura rápida",
                "A data da última varredura rápida não pôde ser determinada.",
                error_code="AV_SCAN_AGE_UNKNOWN",
                details={"defender_error": defender.get("error", "")},
            )
        )

    idade_full = defender.get("full_scan_age_days")
    if isinstance(idade_full, int) and idade_full > FULL_SCAN_MAX_AGE_DAYS:
        achados.append(
            SecurityFinding(
                key="av.full_scan_stale",
                label="Última varredura completa",
                status=CheckStatus.WARN,
                severity=Severity.LOW,
                message=(
                    f"A varredura completa do Defender aconteceu há "
                    f"{idade_full} dia(s) (limite de {FULL_SCAN_MAX_AGE_DAYS})."
                ),
                impact=(
                    "Infecções escondidas em áreas não varridas pela varredura "
                    "rápida podem permanecer no endpoint."
                ),
                remediation=(
                    "Agendar varreduras completas periódicas e acompanhar a "
                    "execução."
                ),
                reference="Microsoft Learn: microsoft-defender-antivirus",
                details={"full_scan_age_days": idade_full},
            )
        )

    # 5. Produtos registrados sem proteção, como informação de contexto.
    if desativados and ativos:
        achados.append(
            SecurityFinding(
                key="av.secondary_disabled",
                label="Produtos antivírus registrados",
                status=CheckStatus.PASS,
                severity=Severity.INFO,
                message=(
                    "Produto registrado sem proteção ativa (outro produto está "
                    "protegendo o endpoint): "
                    + ", ".join(item["name"] for item in desativados)
                    + "."
                ),
                details={"products": desativados},
            )
        )

    return achados


# --------------------------------------------------------------------------
# Configurações básicas de segurança
# --------------------------------------------------------------------------
def classify_settings(section: dict[str, Any] | None) -> list[SecurityFinding]:
    """Interpreta UAC, bloqueio de tela, acesso remoto, disco e conta Guest."""
    if not section:
        return [
            _inconclusive(
                "settings.unavailable",
                "Configurações de segurança",
                "A coleta não retornou a seção de configurações de segurança.",
                error_code="MISSING_SECTION",
            )
        ]

    achados: list[SecurityFinding] = []
    uac = section.get("uac") if isinstance(section.get("uac"), dict) else {}
    tela = section.get("screen_lock") if isinstance(section.get("screen_lock"), dict) else {}
    remoto = (
        section.get("remote_desktop")
        if isinstance(section.get("remote_desktop"), dict)
        else {}
    )
    disco = (
        section.get("encryption") if isinstance(section.get("encryption"), dict) else {}
    )
    guest = (
        section.get("guest_account")
        if isinstance(section.get("guest_account"), dict)
        else {}
    )

    # UAC
    if not uac.get("available"):
        achados.append(
            _inconclusive(
                "settings.uac.unknown",
                "Controle de contas de usuário (UAC)",
                "O estado do UAC não pôde ser lido neste endpoint.",
                error_code="UAC_UNAVAILABLE",
                details={"error": str(uac.get("error", ""))[:400]},
            )
        )
    elif uac.get("enabled") is False:
        achados.append(
            SecurityFinding(
                key="settings.uac.disabled",
                label="Controle de contas de usuário (UAC)",
                status=CheckStatus.FAIL,
                severity=Severity.HIGH,
                message="O Controle de contas de usuário (UAC) está desativado.",
                impact=(
                    "Sem UAC, programas e instaladores obtêm privilégios "
                    "administrativos sem qualquer confirmação do usuário: uma "
                    "instalação de malware deixa de exigir interação."
                ),
                remediation=(
                    "Reativar o Controle de contas de usuário nas Configurações "
                    "de conta do Windows e manter o nível padrão de aviso."
                ),
                reference="Microsoft Learn: user-account-control",
                details={"enabled": False},
            )
        )
    else:
        achados.append(
            SecurityFinding(
                key="settings.uac.enabled",
                label="Controle de contas de usuário (UAC)",
                status=CheckStatus.PASS,
                severity=Severity.INFO,
                message="O Controle de contas de usuário (UAC) está ativo.",
                details={"enabled": True},
            )
        )
        if uac.get("consent_prompt_behavior") == 0:
            achados.append(
                SecurityFinding(
                    key="settings.uac.no_prompt",
                    label="Aviso do UAC",
                    status=CheckStatus.WARN,
                    severity=Severity.MEDIUM,
                    message=(
                        "O UAC está ativo, mas configurado para não pedir "
                        "confirmação ao administrador (ConsentPromptBehaviorAdmin = 0)."
                    ),
                    impact=(
                        "Programas que pedem elevação de privilégio passam sem "
                        "aviso, e o usuário não tem como recusar a operação."
                    ),
                    remediation=(
                        "Definir o aviso do UAC para o nível padrão "
                        "(ConsentPromptBehaviorAdmin = 5)."
                    ),
                    reference="Microsoft Learn: user-account-control",
                    details={"consent_prompt_behavior": 0},
                )
            )
        if uac.get("prompt_on_secure_desktop") is False:
            achados.append(
                SecurityFinding(
                    key="settings.uac.no_secure_desktop",
                    label="Área de trabalho segura do UAC",
                    status=CheckStatus.WARN,
                    severity=Severity.LOW,
                    message=(
                        "O UAC não exibe o aviso na área de trabalho segura."
                    ),
                    impact=(
                        "O prompt de elevação deixa de ser exibido em uma "
                        "surface de bloqueio, permitindo que um programa "
                        "malicioso simule a janela."
                    ),
                    remediation=(
                        "Ativar a opção de exibir os avisos na área de trabalho "
                        "segura (PromptOnSecureDesktop = 1)."
                    ),
                    reference="Microsoft Learn: user-account-control",
                    details={"prompt_on_secure_desktop": False},
                )
            )

    # Bloqueio de tela
    if not tela.get("available"):
        achados.append(
            _inconclusive(
                "settings.screen_lock.unknown",
                "Bloqueio de tela",
                "A configuração de bloqueio de tela não pôde ser lida.",
                error_code="SCREEN_LOCK_UNAVAILABLE",
                details={"error": str(tela.get("error", ""))[:400]},
            )
        )
    elif tela.get("screensaver_active") is False:
        achados.append(
            SecurityFinding(
                key="settings.screen_lock.disabled",
                label="Bloqueio de tela",
                status=CheckStatus.FAIL,
                severity=Severity.MEDIUM,
                message="O protetor de tela está desativado.",
                impact=(
                    "A estação de trabalho não se bloqueia sozinha: quem estiver "
                    "perto do endpoint encontra a sessão aberta, com e-mail e "
                    "sistemas internos acessíveis."
                ),
                remediation=(
                    "Ativar o protetor de tela com tempo de espera e senha nas "
                    "Configurações de tela do Windows."
                ),
                reference="Microsoft Learn: screen-saver-settings",
                details={"screensaver_active": False},
            )
        )
    else:
        achados.append(
            SecurityFinding(
                key="settings.screen_lock.active",
                label="Bloqueio de tela",
                status=CheckStatus.PASS,
                severity=Severity.INFO,
                message="O protetor de tela está ativo.",
                details={"screensaver_active": True},
            )
        )
        if tela.get("password_protected") is False:
            achados.append(
                SecurityFinding(
                    key="settings.screen_lock.no_password",
                    label="Senha do protetor de tela",
                    status=CheckStatus.FAIL,
                    severity=Severity.MEDIUM,
                    message="O protetor de tela está ativo, mas não exige senha.",
                    impact=(
                        "Desbloquear a tela exige apenas um clique: o protetor "
                        "não impede o acesso de quem esteja junto ao endpoint."
                    ),
                    remediation=(
                        "Marcar a opção que exige senha para desbloquear o "
                        "protetor de tela."
                    ),
                    reference="Microsoft Learn: screen-saver-settings",
                    details={"password_protected": False},
                )
            )
        elif tela.get("password_protected") is None:
            achados.append(
                _inconclusive(
                    "settings.screen_lock.password_unknown",
                    "Senha do protetor de tela",
                    "Não foi possível determinar se o protetor de tela exige "
                    "senha para desbloquear.",
                    error_code="SCREEN_LOCK_PASSWORD_UNKNOWN",
                    details={"password_protected": None},
                )
            )

        timeout = tela.get("timeout_seconds")
        if isinstance(timeout, int):
            if timeout > SCREEN_LOCK_MAX_TIMEOUT_SECONDS:
                achados.append(
                    SecurityFinding(
                        key="settings.screen_lock.long_timeout",
                        label="Tempo de bloqueio de tela",
                        status=CheckStatus.WARN,
                        severity=Severity.LOW,
                        message=(
                            f"A tela só é bloqueada após {timeout} segundos "
                            f"(limite de {SCREEN_LOCK_MAX_TIMEOUT_SECONDS})."
                        ),
                        impact=(
                            "Uma sessão exposta permanece utilizável por tempo "
                            "prolongado após o usuário se afastar do endpoint."
                        ),
                        remediation=(
                            "Reduzir o tempo de espera do protetor de tela para "
                            "no máximo 15 minutos."
                        ),
                        reference="Microsoft Learn: screen-saver-settings",
                        details={"timeout_seconds": timeout},
                    )
                )
        else:
            achados.append(
                _inconclusive(
                    "settings.screen_lock.timeout_unknown",
                    "Tempo de bloqueio de tela",
                    "O tempo de bloqueio de tela não pôde ser determinado "
                    "(a configuração pode vir de política de grupo).",
                    error_code="SCREEN_LOCK_TIMEOUT_UNKNOWN",
                    details={"timeout_seconds": timeout},
                )
            )

    # Acesso remoto
    if not remoto.get("available"):
        achados.append(
            _inconclusive(
                "settings.remote_desktop.unknown",
                "Acesso remoto (RDP)",
                "A configuração de acesso remoto não pôde ser lida.",
                error_code="RDP_UNAVAILABLE",
                details={"error": str(remoto.get("error", ""))[:400]},
            )
        )
    elif remoto.get("enabled") is True:
        achados.append(
            SecurityFinding(
                key="settings.remote_desktop.enabled",
                label="Acesso remoto (RDP)",
                status=CheckStatus.WARN,
                severity=Severity.LOW,
                message="O acesso remoto por Área de Trabalho Remota está habilitado.",
                impact=(
                    "O endpoint aceita sessões remotas: uma senha vazia ou "
                    "fraca, ou uma sessão já aberta, pode dar acesso ao "
                    "computador a partir da rede."
                ),
                remediation=(
                    "Desativar o acesso remoto se ele não for necessário, ou "
                    "restringir por firewall e exigir autenticação em dois "
                    "fatores."
                ),
                reference="Microsoft Learn: remote-desktop",
                details={"enabled": True},
            )
        )
    else:
        achados.append(
            SecurityFinding(
                key="settings.remote_desktop.disabled",
                label="Acesso remoto (RDP)",
                status=CheckStatus.PASS,
                severity=Severity.INFO,
                message="O acesso remoto por Área de Trabalho Remota está desativado.",
                details={"enabled": False},
            )
        )

    # Criptografia de disco
    if not disco.get("available"):
        achados.append(
            _inconclusive(
                "settings.encryption.unknown",
                "Criptografia do disco",
                "O estado do BitLocker não pôde ser consultado neste endpoint.",
                error_code="BITLOCKER_UNAVAILABLE",
                details={"error": str(disco.get("error", ""))[:400]},
            )
        )
    elif str(disco.get("protection_status", "")) == "Off":
        achados.append(
            SecurityFinding(
                key="settings.encryption.off",
                label="Criptografia do disco",
                status=CheckStatus.FAIL,
                severity=Severity.MEDIUM,
                message="O volume do sistema não está protegido pelo BitLocker.",
                impact=(
                    "Sem criptografia, o conteúdo do disco fica legível por "
                    "qualquer pessoa que tenha acesso físico ao equipamento ou "
                    "ao volume roubado."
                ),
                remediation=(
                    "Ativar o BitLocker no volume do sistema e guardar a chave "
                    "de recuperação em local seguro."
                ),
                reference="Microsoft Learn: bitlocker-overview",
                details={"protection_status": "Off"},
            )
        )
    else:
        achados.append(
            SecurityFinding(
                key="settings.encryption.on",
                label="Criptografia do disco",
                status=CheckStatus.PASS,
                severity=Severity.INFO,
                message=(
                    "O volume do sistema está protegido pelo BitLocker "
                    f"({disco.get('protection_status') or 'informação disponível'})."
                ),
                details={
                    "protection_status": disco.get("protection_status"),
                    "volume_status": disco.get("volume_status"),
                },
            )
        )

    # Conta Guest
    if not guest.get("available"):
        achados.append(
            _inconclusive(
                "settings.guest.unknown",
                "Conta de convidado (Guest)",
                "Não foi possível consultar a conta de convidado.",
                error_code="GUEST_UNAVAILABLE",
                details={"error": str(guest.get("error", ""))[:400]},
            )
        )
    elif guest.get("present") and guest.get("disabled") is False:
        achados.append(
            SecurityFinding(
                key="settings.guest.enabled",
                label="Conta de convidado (Guest)",
                status=CheckStatus.FAIL,
                severity=Severity.MEDIUM,
                message="A conta de convidado (Guest) está habilitada.",
                impact=(
                    "Uma conta genérica, sem vínculo com uma pessoa, permite "
                    "abrir sessão no endpoint sem rastreabilidade."
                ),
                remediation="Desabilitar a conta de convidado nas configurações de contas locais.",
                reference="Microsoft Learn: guest-account",
                details={"present": True, "disabled": False},
            )
        )
    else:
        achados.append(
            SecurityFinding(
                key="settings.guest.absent",
                label="Conta de convidado (Guest)",
                status=CheckStatus.PASS,
                severity=Severity.INFO,
                message="A conta de convidado (Guest) está desabilitada ou não existe.",
                details={"present": bool(guest.get("present"))},
            )
        )

    return achados
