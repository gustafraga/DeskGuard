"""Coletas simuladas para o modo demonstração.

O modo demonstração existe para validar interface, relatórios e fluxos de
atendimento sem depender do estado do computador do operador.

Três garantias obrigatórias:

1. nenhuma coleta simulada toca o sistema real;
2. todo resultado simulado carrega ``simulated=True``;
3. todo resultado simulado carrega marca textual de simulação nas evidências.
"""

from __future__ import annotations

from deskguard.collectors.base import Collector, ProbeContext
from deskguard.domain.enums import Severity
from deskguard.domain.results import CheckResult

_DEMO_MARK = "DADOS SIMULADOS — modo demonstração, não refletem o estado real."


def build_demo_system_overview() -> list[Collector]:
    """Coletores simulados do procedimento ``system.overview``."""

    def demo_windows(ctx: ProbeContext) -> list[CheckResult]:
        return [
            CheckResult.ok(
                "os.version",
                "Versão do Windows",
                "Coleta simulada concluída.",
                evidence={
                    "simulated": True,
                    "notice": _DEMO_MARK,
                    "caption": "Microsoft Windows 10 Pro (exemplo)",
                    "version": "10.0.19045",
                    "build": "19045 (exemplo)",
                    "architecture": "64-bit",
                },
                simulated=True,
            ),
            CheckResult.ok(
                "system.identity",
                "Identidade do equipamento",
                "Coleta simulada concluída.",
                evidence={
                    "simulated": True,
                    "notice": _DEMO_MARK,
                    "computer_name": "EXEMPLO-PC",
                    "manufacturer": "Fabricante Exemplo",
                    "model": "Modelo Exemplo",
                },
                simulated=True,
            ),
            CheckResult.ok(
                "system.uptime",
                "Tempo de atividade",
                "Coleta simulada concluída.",
                evidence={
                    "simulated": True,
                    "notice": _DEMO_MARK,
                    "uptime_hours": 72.5,
                },
                simulated=True,
            ),
            CheckResult.ok(
                "system.hardware",
                "Hardware resumido",
                "Coleta simulada concluída.",
                evidence={
                    "simulated": True,
                    "notice": _DEMO_MARK,
                    "cpu_name": "CPU Exemplo",
                    "logical_processors": 8,
                    "total_memory_gb": 16.0,
                },
                simulated=True,
            ),
        ]

    def demo_runtime(ctx: ProbeContext) -> CheckResult:
        return CheckResult.ok(
            "system.runtime",
            "Contexto de execução",
            "Coleta simulada concluída.",
            evidence={
                "simulated": True,
                "notice": _DEMO_MARK,
                "is_admin": False,
                "cpu_count": 8,
            },
            simulated=True,
        )

    def demo_storage(ctx: ProbeContext) -> CheckResult:
        return CheckResult.ok(
            "system.storage",
            "Armazenamento",
            "Coleta simulada concluída.",
            evidence={
                "simulated": True,
                "notice": _DEMO_MARK,
                "volumes": [
                    {
                        "path": "C:\\",
                        "total_gb": 476.9,
                        "free_gb": 210.4,
                        "used_percent": 55.9,
                    }
                ],
            },
            simulated=True,
        )

    return [
        Collector(
            check_id="system.windows",
            title="Inventário via PowerShell (simulado)",
            description="Dados simulados para demonstração.",
            fn=demo_windows,
        ),
        Collector(
            check_id="system.runtime",
            title="Contexto de execução (simulado)",
            description="Dados simulados para demonstração.",
            fn=demo_runtime,
        ),
        Collector(
            check_id="system.storage",
            title="Armazenamento (simulado)",
            description="Dados simulados para demonstração.",
            fn=demo_storage,
        ),
    ]


def build_demo_network_configuration() -> list[Collector]:
    """Coletores simulados do procedimento ``network.configuration``."""

    def demo_network(ctx: ProbeContext) -> list[CheckResult]:
        evidence = {
            "simulated": True,
            "notice": _DEMO_MARK,
            "adapters": [
                {
                    "name": "Ethernet",
                    "status": "Up",
                    "media_type": "802.3",
                    "link_speed": "100 Mbps",
                    "mac_address": "00-00-00-00-00-00 (exemplo)",
                    "virtual": False,
                },
                {
                    "name": "Wi-Fi",
                    "status": "Disconnected",
                    "media_type": "Native 802.11",
                    "link_speed": "",
                    "mac_address": "00-00-00-00-00-00 (exemplo)",
                    "virtual": False,
                },
            ],
        }
        ip_evidence = {
            "simulated": True,
            "notice": _DEMO_MARK,
            "interface": "Ethernet",
            "addresses": [
                {
                    "family": "IPv4",
                    "address": "192.168.0.10 (exemplo)",
                    "prefix": 24,
                    "state": "Preferred",
                }
            ],
            "gateways": [{"family": "IPv4", "next_hop": "192.168.0.1 (exemplo)"}],
            "dns_servers": ["192.168.0.1 (exemplo)"],
        }
        routes_evidence = {
            "simulated": True,
            "notice": _DEMO_MARK,
            "default_routes": [
                {
                    "destination": "0.0.0.0/0",
                    "next_hop": "192.168.0.1 (exemplo)",
                    "interface": "Ethernet",
                }
            ],
        }
        profile_evidence = {
            "simulated": True,
            "notice": _DEMO_MARK,
            "profiles": [
                {
                    "interface": "Ethernet",
                    "name": "Rede Corporativa (exemplo)",
                    "category": "DomainAuthenticated",
                    "ipv4_state": "Internet",
                    "ipv6_state": "NoTraffic",
                }
            ],
        }
        return [
            CheckResult.ok(
                "network.interfaces",
                "Estado dos adaptadores",
                "Coleta simulada concluída.",
                evidence=evidence,
                simulated=True,
            ),
            CheckResult.ok(
                "network.ip_configuration",
                "Endereçamento IP",
                "Coleta simulada concluída.",
                evidence=ip_evidence,
                simulated=True,
            ),
            CheckResult.ok(
                "network.routes",
                "Rotas",
                "Coleta simulada concluída.",
                evidence=routes_evidence,
                simulated=True,
            ),
            CheckResult.ok(
                "network.profile",
                "Perfil de rede",
                "Coleta simulada concluída.",
                evidence=profile_evidence,
                simulated=True,
            ),
        ]

    return [
        Collector(
            check_id="network.configuration",
            title="Configuração de rede (simulado)",
            description="Configuração de rede simulada para demonstração.",
            fn=demo_network,
        )
    ]


def build_demo_network_connectivity() -> list[Collector]:
    """Coletores simulados do procedimento ``network.connectivity``."""

    def demo_connectivity(ctx: ProbeContext) -> list[CheckResult]:
        targets = [
            {
                "host": "intranet.exemplo.local",
                "source": "allowlist",
                "description": "Portal corporativo (exemplo)",
                "dns": {
                    "resolved": True,
                    "addresses": ["192.168.0.20 (exemplo)"],
                    "error": "",
                },
                "icmp": {
                    "attempted": True,
                    "reachable": True,
                    "status": "Success",
                    "rtt_ms": 2,
                    "error": "",
                },
                "tcp": [
                    {"port": 443, "state": "aberta", "error": ""},
                ],
            },
            {
                "host": "localhost",
                "source": "implicit",
                "description": "Loopback local do próprio endpoint",
                "dns": {
                    "resolved": True,
                    "addresses": ["127.0.0.1"],
                    "error": "",
                },
                "icmp": {
                    "attempted": True,
                    "reachable": True,
                    "status": "Success",
                    "rtt_ms": 0,
                    "error": "",
                },
                "tcp": [],
            },
        ]
        context = {
            "simulated": True,
            "notice": _DEMO_MARK,
            "allowlist": {"available": True, "count": 1},
            "rejected_targets": [],
        }
        return [
            CheckResult.ok(
                "network.dns",
                "Resolução DNS",
                "Coleta simulada concluída.",
                evidence={**context, "results": targets},
                simulated=True,
            ),
            CheckResult.ok(
                "network.icmp",
                "Alcance ICMP",
                "Coleta simulada concluída.",
                evidence={**context, "results": targets},
                simulated=True,
            ),
            CheckResult.ok(
                "network.tcp",
                "Portas TCP",
                "Coleta simulada concluída.",
                evidence={**context, "results": targets},
                simulated=True,
            ),
        ]

    return [
        Collector(
            check_id="network.connectivity",
            title="Conectividade de rede (simulado)",
            description="Sondagens de rede simuladas para demonstração.",
            fn=demo_connectivity,
        )
    ]


def build_demo_printers_status() -> list[Collector]:
    """Coletores simulados do procedimento ``printers.status``."""

    def demo_printers(ctx: ProbeContext) -> list[CheckResult]:
        inventory = {
            "simulated": True,
            "notice": _DEMO_MARK,
            "count": 2,
            "printers": [
                {
                    "name": "Impressora Corporativa (exemplo)",
                    "port": "192.168.0.30 (exemplo)",
                    "driver": "Driver Corporativo",
                    "is_network": True,
                    "is_local": False,
                    "printer_status": 1,
                    "detected_error_state": 0,
                    "extended_status": 2,
                    "work_offline": False,
                    "is_default": True,
                },
                {
                    "name": "Microsoft Print to PDF",
                    "port": "PORTPROMPT:",
                    "driver": "Microsoft Software Printer Driver",
                    "is_network": False,
                    "is_local": True,
                    "printer_status": 3,
                    "detected_error_state": 0,
                    "extended_status": 2,
                    "work_offline": False,
                    "is_default": False,
                },
            ],
        }
        queue = {
            "simulated": True,
            "notice": _DEMO_MARK,
            "included": True,
            "queues": [
                {
                    "printer": "Impressora Corporativa (exemplo)",
                    "count": 0,
                    "jobs": [],
                }
            ],
        }
        spooler = {
            "simulated": True,
            "notice": _DEMO_MARK,
            "name": "Spooler",
            "status": "Running",
            "start_type": "Automatic",
            "available": True,
        }
        return [
            CheckResult.ok(
                "printers.inventory",
                "Inventário de impressoras",
                "Coleta simulada concluída.",
                evidence=inventory,
                simulated=True,
            ),
            CheckResult.ok(
                "printers.queue",
                "Fila de impressão",
                "Coleta simulada concluída.",
                evidence=queue,
                simulated=True,
            ),
            CheckResult.ok(
                "printers.spooler",
                "Serviço de impressão",
                "Coleta simulada concluída.",
                evidence=spooler,
                simulated=True,
            ),
        ]

    return [
        Collector(
            check_id="printers.status",
            title="Estado das impressoras (simulado)",
            description="Estado de impressoras e fila simulados para demonstração.",
            fn=demo_printers,
        )
    ]


def build_demo_services_status() -> list[Collector]:
    """Coletores simulados do procedimento ``services.status``."""

    def demo_services(ctx: ProbeContext) -> list[CheckResult]:
        services = [
            {
                "name": "Spooler",
                "display_name": "Print Spooler",
                "status": "Running",
                "start_type": "Automatic",
                "path": "C:\\Windows\\System32\\spoolsv.exe",
                "exit_code": 0,
                "service_type": "Own Process",
                "depends_on": ["RPCSS"],
                "dependents": [],
                "found": True,
            },
            {
                "name": "Dnscache",
                "display_name": "DNS Client",
                "status": "Running",
                "start_type": "Automatic",
                "path": "C:\\Windows\\system32\\svchost.exe",
                "exit_code": 0,
                "service_type": "Share Process",
                "depends_on": ["nsi"],
                "dependents": [],
                "found": True,
            },
            {
                "name": "DHCP",
                "display_name": "DHCP Client",
                "status": "Running",
                "start_type": "Automatic",
                "path": "C:\\Windows\\system32\\svchost.exe",
                "exit_code": 0,
                "service_type": "Share Process",
                "depends_on": ["Afd"],
                "dependents": ["NlaSvc"],
                "found": True,
            },
            {
                "name": "WlanSvc",
                "display_name": "WLAN AutoConfig",
                "status": "Running",
                "start_type": "Automatic",
                "path": "C:\\Windows\\system32\\svchost.exe",
                "exit_code": 0,
                "service_type": "Share Process",
                "depends_on": ["RpcSs"],
                "dependents": [],
                "found": True,
            },
            {
                "name": "wuauserv",
                "display_name": "Windows Update",
                "status": "Stopped",
                "start_type": "Manual",
                "path": "C:\\Windows\\system32\\svchost.exe",
                "exit_code": 0,
                "service_type": "Share Process",
                "depends_on": ["rpcss"],
                "dependents": [],
                "found": True,
            },
            {
                "name": "BITS",
                "display_name": "Background Intelligent Transfer Service",
                "status": "Stopped",
                "start_type": "Manual",
                "path": "C:\\Windows\\system32\\svchost.exe",
                "exit_code": 0,
                "service_type": "Share Process",
                "depends_on": ["RpcSs"],
                "dependents": [],
                "found": True,
            },
            {
                "name": "winmgmt",
                "display_name": "Windows Management Instrumentation",
                "status": "Running",
                "start_type": "Automatic",
                "path": "C:\\Windows\\system32\\svchost.exe",
                "exit_code": 0,
                "service_type": "Share Process",
                "depends_on": ["RPCSS"],
                "dependents": [],
                "found": True,
            },
            {
                "name": "RpcSs",
                "display_name": "Remote Procedure Call (RPC)",
                "status": "Running",
                "start_type": "Automatic",
                "path": "C:\\Windows\\system32\\svchost.exe",
                "exit_code": 0,
                "service_type": "Share Process",
                "depends_on": ["DcomLaunch"],
                "dependents": [],
                "found": True,
            },
            {
                "name": "DcomLaunch",
                "display_name": "DCOM Server Process Launcher",
                "status": "Running",
                "start_type": "Automatic",
                "path": "C:\\Windows\\system32\\svchost.exe",
                "exit_code": 0,
                "service_type": "Share Process",
                "depends_on": [],
                "dependents": [],
                "found": True,
            },
            {
                "name": "DPS",
                "display_name": "Diagnostic Policy Service",
                "status": "Running",
                "start_type": "Automatic",
                "path": "C:\\Windows\\system32\\svchost.exe",
                "exit_code": 0,
                "service_type": "Share Process",
                "depends_on": [],
                "dependents": [],
                "found": True,
            },
        ]

        dependencies = [
            {
                "name": servico["name"],
                "depends_on": servico["depends_on"],
                "dependents": servico["dependents"],
            }
            for servico in services
        ]

        contexto = {"simulated": True, "notice": _DEMO_MARK}

        inventario = {
            **contexto,
            "count": len(services),
            "services": services,
        }
        cadeia = {
            **contexto,
            "count": len(dependencies),
            "dependencies": dependencies,
        }

        return [
            CheckResult.ok(
                "services.inventory",
                "Estado dos serviços",
                "Coleta simulada concluída.",
                evidence=inventario,
                simulated=True,
            ),
            CheckResult.ok(
                "services.startup",
                "Tipo de inicialização",
                "Coleta simulada concluída.",
                evidence=inventario,
                simulated=True,
            ),
            CheckResult.ok(
                "services.dependencies",
                "Dependências entre serviços",
                "Coleta simulada concluída.",
                evidence=cadeia,
                simulated=True,
            ),
        ]

    return [
        Collector(
            check_id="services.status",
            title="Estado dos serviços (simulado)",
            description="Estado de serviços e dependências simulados para demonstração.",
            fn=demo_services,
        )
    ]


def build_demo_security_audit() -> list[Collector]:
    """Coletores simulados do procedimento ``security.audit``.

    O cenário simulado reproduz um endpoint razoavelmente configurado, com
    dois desvios de baixa severidade (acesso remoto habilitado e tempo de
    bloqueio de tela longo) e um item inconclusivo (criptografia de disco sem
    privilégio elevado), para exercitar os três desfechos possíveis do
    relatório.
    """

    def demo_security(ctx: ProbeContext) -> list[CheckResult]:
        contexto = {"simulated": True, "notice": _DEMO_MARK}

        firewall = {
            **contexto,
            "available": True,
            "count": 3,
            "profiles": [
                {
                    "name": "Domain",
                    "enabled": "True",
                    "default_inbound_action": "NotConfigured",
                    "default_outbound_action": "NotConfigured",
                    "allow_inbound_rules": "NotConfigured",
                },
                {
                    "name": "Private",
                    "enabled": "True",
                    "default_inbound_action": "NotConfigured",
                    "default_outbound_action": "NotConfigured",
                    "allow_inbound_rules": "NotConfigured",
                },
                {
                    "name": "Public",
                    "enabled": "True",
                    "default_inbound_action": "NotConfigured",
                    "default_outbound_action": "NotConfigured",
                    "allow_inbound_rules": "NotConfigured",
                },
            ],
            "error": "",
            "module_error": "",
        }

        antivirus = {
            **contexto,
            "available": True,
            "defender": {
                **contexto,
                "available": True,
                "antivirus_enabled": True,
                "realtime_protection": True,
                "antispyware_enabled": True,
                "behavior_monitor_enabled": True,
                "signature_version": "1.423.0.0 (exemplo)",
                "signature_age_days": 1,
                "signature_last_updated": "2026-10-20T03:10:00",
                "quick_scan_age_days": 9,
                "full_scan_age_days": 12,
                "error": "",
            },
            "products": [
                {
                    "name": "Windows Defender (exemplo)",
                    "product_state": "393472",
                    "registered_at": "2026-06-15T09:57:25",
                }
            ],
            "product_count": 1,
            "error": "",
            "products_error": "",
        }

        settings = {
            **contexto,
            "available": True,
            "uac": {
                **contexto,
                "available": True,
                "enabled": True,
                "consent_prompt_behavior": 5,
                "prompt_on_secure_desktop": True,
                "error": "",
            },
            "screen_lock": {
                **contexto,
                "available": True,
                "screensaver_active": True,
                "timeout_seconds": 1800,
                "password_protected": True,
                "error": "",
            },
            "remote_desktop": {
                **contexto,
                "available": True,
                "enabled": True,
                "error": "",
            },
            "encryption": {
                **contexto,
                "available": False,
                "system_volume": "",
                "protection_status": "",
                "volume_status": "",
                "error": "A leitura do estado do BitLocker exige privilegio elevado.",
            },
            "guest_account": {
                **contexto,
                "available": True,
                "present": False,
                "disabled": None,
                "error": "",
            },
            "error": "",
        }

        return [
            CheckResult.ok(
                "security.firewall",
                "Windows Firewall por perfil",
                "Coleta simulada concluída.",
                evidence=firewall,
                simulated=True,
            ),
            CheckResult.warning(
                "security.antivirus",
                "Proteção antivírus",
                "[Média] Última varredura rápida: a varredura rápida do Defender "
                "aconteceu há 9 dia(s) (limite de 7).",
                evidence=antivirus,
                severity=Severity.MEDIUM,
                remediation=(
                    "Executar uma varredura rápida e configurar a varredura "
                    "automática com frequência."
                ),
                simulated=True,
            ),
            CheckResult.warning(
                "security.settings",
                "Configurações de segurança",
                "[Baixa] Acesso remoto (RDP): o acesso remoto por Área de "
                "Trabalho Remota está habilitado. [Baixa] Tempo de bloqueio de "
                "tela: a tela só é bloqueada após 1800 segundos (limite de 900).",
                evidence=settings,
                remediation=(
                    "Desativar o acesso remoto se ele não for necessário e "
                    "reduzir o tempo de espera do protetor de tela."
                ),
                simulated=True,
            ),
        ]

    return [
        Collector(
            check_id="security.audit",
            title="Auditoria de segurança (simulada)",
            description="Achados de segurança simulados para demonstração.",
            fn=demo_security,
        )
    ]


def build_demo_ad_self_status() -> list[Collector]:
    """Coletores simulados do procedimento ``ad.self_status``."""

    def demo_ad(ctx: ProbeContext) -> list[CheckResult]:
        account = {
            "simulated": True,
            "notice": _DEMO_MARK,
            "username": "tecnico.exemplo",
            "user_domain": "EMPRESA",
            "available": True,
            "enabled": True,
            "locked_out": False,
            "password_expired": False,
            "account_expiration_date": "2026-12-31T00:00:00",
            "last_logon_date": "2026-10-23T09:15:00",
            "error": "",
        }
        trust = {
            "simulated": True,
            "notice": _DEMO_MARK,
            "checked": True,
            "trust_ok": True,
            "domain": "empresa.local (exemplo)",
            "error": "",
        }
        return [
            CheckResult.ok(
                "ad.account",
                "Conta do usuário logado",
                "Coleta simulada concluída.",
                evidence=account,
                simulated=True,
            ),
            CheckResult.ok(
                "ad.domain_trust",
                "Confiança do domínio",
                "Coleta simulada concluída.",
                evidence=trust,
                simulated=True,
            ),
        ]

    return [
        Collector(
            check_id="ad.self_status",
            title="Active Directory do usuário logado (simulado)",
            description="Conta e confiança do domínio simuladas para demonstração.",
            fn=demo_ad,
        )
    ]
