"""Procedimentos de Manutenção do Sistema (Auto-Remediação)."""

from __future__ import annotations

from typing import Any

from deskguard.catalog.registry import register
from deskguard.collectors.base import Collector, ProbeContext
from deskguard.collectors.powershell import PowerShellRunner, script_path
from deskguard.domain.enums import Capability, ExecutionMode, PrivilegeLevel
from deskguard.domain.results import CheckResult
from deskguard.domain.spec import ProcedureSpec, StepSpec
from deskguard.errors import CollectorError
from deskguard.procedures.base import Procedure


@register
class FlushDnsProcedure(Procedure):
    """Limpeza do cache DNS do sistema (ipconfig /flushdns)."""

    spec = ProcedureSpec(
        id="maintenance.flush_dns",
        title="Limpar Cache DNS",
        category="Manutenção",
        summary="Executa ipconfig /flushdns para redefinir o cache de resolução de nomes.",
        description=(
            "Executa o comando nativo ipconfig /flushdns para limpar o cache DNS "
            "do Windows, resolvendo falhas de navegação e resolução de nomes."
        ),
        capability=Capability.READ_ONLY,
        privilege=PrivilegeLevel.USER,
        risk_notes=(
            "Nenhuma configuração de rede permanente é alterada.",
            "Operação totalmente segura e instantânea.",
        ),
        prerequisites=("Sistema operacional Windows.",),
        expected_outcomes=(
            "Cache DNS limpo com sucesso.",
        ),
        steps=(
            StepSpec(
                id="dns.flush",
                title="Redefinição do cache DNS",
                description="Execução de ipconfig /flushdns.",
            ),
        ),
        version="1.0.0",
        tags=("dns", "rede", "manutenção", "cache"),
    )

    def build_collectors(self) -> list[Collector]:
        return [
            Collector(
                check_id="dns.flush",
                title="Limpar Cache DNS",
                description="Executa o comando ipconfig /flushdns.",
                fn=self._collect,
            )
        ]

    def build_demo_collectors(self) -> list[Collector]:
        return [
            Collector(
                check_id="dns.flush",
                title="Limpar Cache DNS (Simulado)",
                description="Simulação de limpeza de cache DNS.",
                fn=lambda ctx: [CheckResult.ok("dns.flush", "Redefinição do cache DNS", "Cache DNS limpo com sucesso (Simulado).", evidence={"simulated": True})],
            )
        ]

    def _collect(self, ctx: ProbeContext) -> list[CheckResult]:
        runner = PowerShellRunner()
        try:
            outcome = runner.run_command("ipconfig /flushdns", timeout_s=ctx.timeout_s)
        except CollectorError as exc:
            return [
                CheckResult.inconclusive(
                    "dns.flush",
                    "Redefinição do cache DNS",
                    "Não foi possível executar o comando ipconfig.",
                    error_code="COMMAND_UNAVAILABLE",
                    evidence={"detail": str(exc)},
                )
            ]

        if not outcome.ok:
            return [
                CheckResult.fail(
                    "dns.flush",
                    "Redefinição do cache DNS",
                    "O comando ipconfig /flushdns falhou.",
                    evidence={"stderr": outcome.stderr},
                )
            ]

        return [
            CheckResult.ok(
                "dns.flush",
                "Redefinição do cache DNS",
                "Cache DNS limpo com sucesso.",
                evidence={"stdout": outcome.stdout.strip()},
            )
        ]


@register
class CleanTempFilesProcedure(Procedure):
    """Limpeza de arquivos temporários do usuário e do sistema."""

    spec = ProcedureSpec(
        id="maintenance.clean_temp_files",
        title="Limpar Arquivos Temporários",
        category="Manutenção",
        summary="Remove arquivos temporários obsoletos para liberar espaço em disco.",
        description=(
            "Remove arquivos temporários localizados na pasta TEMP do usuário e "
            "na pasta Temp do Windows, otimizando o espaço de armazenamento."
        ),
        capability=Capability.MODIFYING,
        privilege=PrivilegeLevel.USER,
        risk_notes=(
            "Apenas arquivos temporários não bloqueados em uso são removidos.",
            "Nenhum dado pessoal ou documento do usuário é afetado.",
        ),
        prerequisites=("Permissão de escrita nas pastas temporárias do sistema.",),
        expected_outcomes=(
            "Arquivos temporários obsoletos removidos com sucesso.",
        ),
        steps=(
            StepSpec(
                id="temp.clean",
                title="Limpeza de arquivos temporários",
                description="Varredura e remoção de arquivos em %TEMP% e C:\\Windows\\Temp.",
            ),
        ),
        version="1.0.0",
        tags=("temporários", "disco", "limpeza", "manutenção"),
    )

    def build_collectors(self) -> list[Collector]:
        return [
            Collector(
                check_id="temp.clean",
                title="Limpeza de Arquivos Temporários",
                description="Executa script de remoção de arquivos temporários.",
                fn=self._collect,
            )
        ]

    def build_demo_collectors(self) -> list[Collector]:
        return [
            Collector(
                check_id="temp.clean",
                title="Limpeza de Arquivos Temporários (Simulado)",
                description="Simulação de limpeza de temporários.",
                fn=lambda ctx: [CheckResult.ok("temp.clean", "Limpeza de arquivos temporários", "Removidos 45 arquivos temporários (120 MB) - Simulado.", evidence={"simulated": True})],
            )
        ]

    def _collect(self, ctx: ProbeContext) -> list[CheckResult]:
        runner = PowerShellRunner()
        try:
            outcome = runner.run_script(
                script_path("clean_temp.ps1"),
                {},
                timeout_s=ctx.timeout_s,
            )
        except CollectorError as exc:
            return [
                CheckResult.inconclusive(
                    "temp.clean",
                    "Limpeza de arquivos temporários",
                    "Não foi possível executar a limpeza.",
                    error_code="POWERSHELL_UNAVAILABLE",
                    evidence={"detail": str(exc)},
                )
            ]

        if not outcome.ok:
            return [
                CheckResult.fail(
                    "temp.clean",
                    "Limpeza de arquivos temporários",
                    "A limpeza de temporários encontrou falhas.",
                    evidence={"stderr": outcome.stderr},
                )
            ]

        data = outcome.payload.get("maintenance.temp", {})
        files = data.get("cleaned_files", 0)
        mb = data.get("cleaned_mb", 0)

        return [
            CheckResult.ok(
                "temp.clean",
                "Limpeza de arquivos temporários",
                f"Removidos {files} arquivo(s) temporário(s) liberando aproximadamente {mb} MB.",
                evidence=data,
            )
        ]


@register
class SystemRepairProcedure(Procedure):
    """Reparo do sistema operacional (DISM e SFC)."""

    spec = ProcedureSpec(
        id="maintenance.system_repair",
        title="Reparo e Verificação do Sistema (DISM / SFC)",
        category="Manutenção",
        summary="Executa DISM e SFC para verificar e corrigir arquivos corrompidos do Windows.",
        description=(
            "Executa em sequência as ferramentas DISM (/Online /Cleanup-Image /RestoreHealth) "
            "e SFC (/scannow) para inspecionar e reparar a integridade da imagem e dos "
            "arquivos de sistema do Windows. Atenção: pode levar vários minutos."
        ),
        capability=Capability.MODIFYING,
        privilege=PrivilegeLevel.ELEVATED,
        risk_notes=(
            "Requer privilégios administrativos (Execução elevada).",
            "O processo de varredura e reparo de integridade pode levar vários minutos.",
            "Nenhum arquivo pessoal é apagado ou modificado.",
        ),
        prerequisites=(
            "Privilégios de Administrador na máquina.",
            "Conexão com a internet recomendada para download de arquivos de reparo via DISM.",
        ),
        expected_outcomes=(
            "Integridade da imagem e arquivos do sistema verificados e reparados com sucesso.",
        ),
        steps=(
            StepSpec(
                id="repair.dism",
                title="Reparo de Imagem (DISM)",
                description="Executa DISM /Online /Cleanup-Image /RestoreHealth.",
            ),
            StepSpec(
                id="repair.sfc",
                title="Verificação de Arquivos de Sistema (SFC)",
                description="Executa sfc /scannow.",
            ),
        ),
        version="1.0.0",
        tags=("reparos", "dism", "sfc", "sistema", "corrupção"),
    )

    def build_collectors(self) -> list[Collector]:
        return [
            Collector(
                check_id="repair.dism",
                title="Reparo de Imagem (DISM)",
                description="Executa DISM para restaurar a integridade da imagem do Windows.",
                fn=self._collect_dism,
            ),
            Collector(
                check_id="repair.sfc",
                title="Verificação de Arquivos (SFC)",
                description="Executa sfc /scannow para corrigir arquivos de sistema.",
                fn=self._collect_sfc,
            ),
        ]

    def build_demo_collectors(self) -> list[Collector]:
        return [
            Collector(
                check_id="repair.dism",
                title="Reparo de Imagem (DISM - Simulado)",
                description="Simulação de DISM.",
                fn=lambda ctx: [CheckResult.ok("repair.dism", "Reparo de Imagem (DISM)", "A operação de restauração concluiu com êxito (Simulado).", evidence={"simulated": True})],
            ),
            Collector(
                check_id="repair.sfc",
                title="Verificação de Arquivos (SFC - Simulado)",
                description="Simulação de SFC.",
                fn=lambda ctx: [CheckResult.ok("repair.sfc", "Verificação de Arquivos de Sistema (SFC)", "A Proteção de Recursos do Windows não encontrou nenhuma violação de integridade (Simulado).", evidence={"simulated": True})],
            ),
        ]

    def _collect_dism(self, ctx: ProbeContext) -> list[CheckResult]:
        runner = PowerShellRunner()
        try:
            outcome = runner.run_command("DISM /Online /Cleanup-Image /RestoreHealth", timeout_s=max(120.0, ctx.timeout_s))
        except CollectorError as exc:
            return [
                CheckResult.inconclusive(
                    "repair.dism",
                    "Reparo de Imagem (DISM)",
                    "Não foi possível iniciar o DISM.",
                    error_code="COMMAND_UNAVAILABLE",
                    evidence={"detail": str(exc)},
                )
            ]

        if not outcome.ok:
            return [
                CheckResult.fail(
                    "repair.dism",
                    "Reparo de Imagem (DISM)",
                    "O comando DISM encontrou erros ao reparar a imagem.",
                    evidence={"stderr": outcome.stderr, "stdout": outcome.stdout},
                )
            ]

        return [
            CheckResult.ok(
                "repair.dism",
                "Reparo de Imagem (DISM)",
                "A imagem do sistema foi verificada e reparada com êxito pelo DISM.",
                evidence={"stdout": outcome.stdout.strip()[:600]},
            )
        ]

    def _collect_sfc(self, ctx: ProbeContext) -> list[ProbeContext] | list[CheckResult]:
        runner = PowerShellRunner()
        try:
            outcome = runner.run_command("sfc /scannow", timeout_s=max(120.0, ctx.timeout_s))
        except CollectorError as exc:
            return [
                CheckResult.inconclusive(
                    "repair.sfc",
                    "Verificação de Arquivos de Sistema (SFC)",
                    "Não foi possível iniciar o SFC.",
                    error_code="COMMAND_UNAVAILABLE",
                    evidence={"detail": str(exc)},
                )
            ]

        if not outcome.ok:
            return [
                CheckResult.fail(
                    "repair.sfc",
                    "Verificação de Arquivos de Sistema (SFC)",
                    "O SFC encontrou falhas ou arquivos corrompidos que não pôde reparar.",
                    evidence={"stderr": outcome.stderr, "stdout": outcome.stdout},
                )
            ]

        return [
            CheckResult.ok(
                "repair.sfc",
                "Verificação de Arquivos de Sistema (SFC)",
                "O verificador de arquivos do sistema (SFC) concluiu a varredura sem corrupções críticas.",
                evidence={"stdout": outcome.stdout.strip()[:600]},
            )
        ]
