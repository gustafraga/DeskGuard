"""Interface de linha de comando do DeskGuard.

A CLI é o caminho mais direto para executar uma verificação no próprio
Windows, sem navegador. Ela usa exatamente o mesmo motor de execução e o
mesmo gerador de relatório da interface web.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from deskguard.catalog import registry
from deskguard.config import Settings
from deskguard.desktop import desktop_availability
from deskguard.domain.enums import ExecutionMode, Outcome
from deskguard.errors import DeskGuardError
from deskguard.services.execution import ExecutionService
from deskguard.services.report import build_report_markdown, build_report_text
from deskguard.storage.database import Database
from deskguard.version import __version__

_STATUS_LABELS = {
    "pass": "APROVADO",
    "fail": "FALHA CONFIRMADA",
    "warn": "ALERTA",
    "inconclusive": "INCONCLUSIVO",
    "not_applicable": "NÃO APLICÁVEL",
    "skipped": "IGNORADO",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deskguard",
        description="Plataforma local de automação de Service Desk e diagnóstico de endpoints Windows.",
    )
    parser.add_argument("--version", action="version", version=f"DeskGuard {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Inicia a interface web local.")
    serve.add_argument("--host", default=None, help="Endereço de escuta (padrão 127.0.0.1).")
    serve.add_argument("--port", type=int, default=None, help="Porta HTTP (padrão 8765).")
    serve.add_argument("--open", action="store_true", help="Abre o navegador ao iniciar.")

    desktop = sub.add_parser(
        "desktop",
        help="Abre a interface em uma janela nativa do Windows (sem navegador).",
    )
    desktop.add_argument("--host", default=None, help="Endereço de escuta (padrão 127.0.0.1).")
    desktop.add_argument("--port", type=int, default=None, help="Porta HTTP (padrão 8765).")
    desktop.add_argument("--title", default=None, help="Título da janela.")
    desktop.add_argument("--width", type=int, default=None, help="Largura da janela em pixels.")
    desktop.add_argument("--height", type=int, default=None, help="Altura da janela em pixels.")
    desktop.add_argument(
        "--no-reuse",
        action="store_true",
        help="Não reaproveita uma instância do DeskGuard já em execução.",
    )
    desktop.add_argument(
        "--no-browser-fallback",
        action="store_true",
        help="Não abre o navegador se a janela nativa não estiver disponível.",
    )
    desktop.add_argument(
        "--open-browser",
        action="store_true",
        help="Abre também o navegador padrão, junto com a janela nativa.",
    )

    sub.add_parser("list", help="Lista os procedimentos do catálogo.")

    doctor = sub.add_parser("doctor", help="Verifica o ambiente local do DeskGuard.")
    doctor.add_argument("--json", action="store_true", help="Saída em JSON.")

    run = sub.add_parser("run", help="Executa um procedimento e gera o relatório.")
    run.add_argument("procedure_id", help="Identificador do procedimento no catálogo.")
    run.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="NOME=VALOR",
        help="Parâmetro do procedimento. Pode ser repetido.",
    )
    run.add_argument(
        "--mode",
        choices=[ExecutionMode.LIVE.value, ExecutionMode.DEMO.value],
        default=ExecutionMode.LIVE.value,
        help="Origem dos dados (padrão: live).",
    )
    run.add_argument("--json", action="store_true", help="Saída em JSON.")
    run.add_argument("--out", default=None, help="Grava o relatório em um arquivo.")

    targets = sub.add_parser(
        "targets",
        help="Gerencia a lista de destinos autorizados para as sondagens de rede.",
    )
    targets_sub = targets.add_subparsers(dest="targets_command", required=True)

    targets_sub.add_parser("list", help="Lista os destinos autorizados.")

    add = targets_sub.add_parser("add", help="Autoriza um destino para as sondagens.")
    add.add_argument("host", help="Nome de host ou endereço IPv4 do destino.")
    add.add_argument(
        "--port",
        action="append",
        type=int,
        default=[],
        metavar="NUMERO",
        help=(
            "Porta autorizada para teste TCP. Pode ser repetida. "
            "Sem esta opção, valem as portas padrão (80 e 443)."
        ),
    )
    add.add_argument(
        "--description", default="", help="Descrição do destino (texto livre)."
    )
    add.add_argument(
        "--no-ping",
        action="store_true",
        help="Não testa ICMP neste destino (apenas DNS e TCP).",
    )

    remove = targets_sub.add_parser("remove", help="Revoga a autorização de um destino.")
    remove.add_argument("host", help="Nome de host ou endereço IPv4 do destino.")

    return parser


def _parse_params(raw: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for item in raw:
        if "=" not in item:
            raise DeskGuardError(f"Parâmetro inválido '{item}'. Use o formato NOME=VALOR.")
        name, _, value = item.partition("=")
        params[name.strip()] = value.strip()
    return params


def _command_list() -> int:
    registry.load_builtin_procedures()
    specs = registry.list_specs()
    if not specs:
        print("Nenhum procedimento registrado.")
        return 0
    print(f"Catálogo DeskGuard ({len(specs)} procedimento(s))\n")
    current_category = None
    for spec in specs:
        if spec.category != current_category:
            current_category = spec.category
            print(f"\n[{current_category}]")
        capability = "somente leitura" if spec.read_only else "ALTERA O SISTEMA"
        privilege = "usuário" if spec.privilege == "user" else "elevado"
        print(f"  {spec.id:<28} {spec.title}")
        print(f"  {'':<28} {spec.summary}")
        print(f"  {'':<28} {capability} | privilégio: {privilege} | versão {spec.version}")
    print("\nUse 'deskguard run <identificador> --param NOME=VALOR' para executar.")
    return 0


def _command_doctor(settings: Settings) -> int:
    from deskguard.collectors.powershell import PowerShellRunner
    from deskguard.collectors.python_stdlib import is_admin
    import platform
    import sys as _sys

    registry.load_builtin_procedures()
    from deskguard.security.allowlist import load_allowlist

    allowlist = load_allowlist()
    desktop = desktop_availability()
    report = {
        "version": __version__,
        "python": _sys.version.split()[0],
        "platform": platform.platform(),
        "data_dir": str(settings.data_dir),
        "database_path": str(settings.database_path),
        "database_exists": settings.database_path.exists(),
        "powershell_available": PowerShellRunner().available,
        "is_admin": is_admin(),
        "procedures": len(registry.list_specs()),
        "mode": str(settings.mode),
        "allowlist": {
            "path": str(allowlist.path),
            "available": allowlist.available,
            "targets": len(allowlist.targets),
        },
        "desktop": desktop,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _command_run(args: argparse.Namespace, settings: Settings) -> int:
    registry.load_builtin_procedures()
    params = _parse_params(args.param)
    mode = ExecutionMode(args.mode)

    database = Database(settings.database_path)
    database.create_all()
    service = ExecutionService(database, settings)
    try:
        result = service.run_synchronously(
            args.procedure_id, params, mode=mode, actor="cli"
        )
    finally:
        service.shutdown()

    with database.session() as session:
        row = repository_get(session, result.execution_id)
        steps = repository_steps(session, result.execution_id)
        spec = registry.get_spec(result.procedure_id)
        markdown = build_report_markdown(row, steps, spec)

    if args.json:
        payload = {
            "execution_id": result.execution_id,
            "procedure_id": result.procedure_id,
            "status": str(result.status),
            "outcome": str(result.outcome),
            "summary": result.summary,
            "error": result.error,
            "checks": [
                {
                    "check_id": check.check_id,
                    "title": check.title,
                    "status": str(check.status),
                    "severity": str(check.severity),
                    "message": check.message,
                    "evidence": check.evidence,
                }
                for check in result.checks
            ],
            "report_markdown": markdown,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Execução: {result.execution_id}")
        print(f"Procedimento: {result.procedure_id}")
        print(f"Resultado consolidado: {result.outcome}")
        print(f"Resumo: {result.summary}\n")
        for check in result.checks:
            label = _STATUS_LABELS.get(str(check.status), str(check.status).upper())
            print(f"  [{label:<17}] {check.title}: {check.message}")
        if result.error:
            print(f"\nErro: {result.error}")
        print("\n" + "-" * 72)
        print(
            build_report_text(
                build_report_markdown(
                    row, steps, spec, include_dev_details=False
                )
            )
        )

    if args.out:
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(markdown, encoding="utf-8")
        print(f"\nRelatório gravado em: {destination}")

    database.dispose()
    return 0 if result.outcome in (Outcome.HEALTHY, Outcome.ISSUES_FOUND, Outcome.INCONCLUSIVE) else 1


def repository_get(session: Any, execution_id: str) -> Any:
    from deskguard.storage import repository

    return repository.get_execution(session, execution_id)


def repository_steps(session: Any, execution_id: str) -> Any:
    from deskguard.storage import repository

    return repository.get_steps(session, execution_id)


def _command_targets(args: argparse.Namespace) -> int:
    """Gerencia a lista de destinos autorizados para as sondagens de rede."""
    from deskguard.security.allowlist import (
        AllowedTarget,
        AllowlistError,
        load_allowlist,
        save_allowlist,
    )

    current = load_allowlist()

    if args.targets_command == "list":
        if not current.targets:
            print("Nenhum destino autorizado.")
            print(f"  Arquivo: {current.path}")
            print(
                "  Sem autorização explícita, apenas localhost e o gateway padrão "
                "do endpoint são testados."
            )
            return 0
        print(f"Destinos autorizados ({len(current.targets)}):")
        for target in current.targets:
            portas = ", ".join(str(porta) for porta in target.ports) or "-"
            icmp = "sim" if target.ping else "não"
            descricao = f" — {target.description}" if target.description else ""
            print(f"  {target.host:<40} portas: {portas:<12} ping: {icmp}{descricao}")
        print(f"\nArquivo: {current.path}")
        return 0

    if args.targets_command == "add":
        host = str(args.host).strip().lower()
        existing = current.find(host)
        ports = tuple(dict.fromkeys(args.port)) if args.port else None
        if existing is not None and ports is None:
            ports = existing.ports
        try:
            target = AllowedTarget(
                host=host,
                ports=ports or (80, 443),
                description=str(args.description).strip()[:200],
                ping=not args.no_ping,
            )
        except AllowlistError as exc:
            print(f"Erro: {exc}", file=sys.stderr)
            return 2

        updated = [item for item in current.targets if item.host != host]
        updated.append(target)
        path = save_allowlist(updated)
        print(f"Destino autorizado: {host}")
        print(f"  Portas: {', '.join(str(porta) for porta in target.ports)}")
        print(f"  ICMP: {'sim' if target.ping else 'não'}")
        print(f"  Arquivo: {path}")
        return 0

    if args.targets_command == "remove":
        host = str(args.host).strip().lower()
        if current.find(host) is None:
            print(f"Erro: o destino '{host}' não está na lista de autorizados.", file=sys.stderr)
            return 2
        updated = [item for item in current.targets if item.host != host]
        path = save_allowlist(updated)
        print(f"Autorização removida: {host}")
        print(f"  Arquivo: {path}")
        return 0

    return 2


def _command_desktop(args: argparse.Namespace, settings: Settings) -> int:
    """Abre a interface em uma janela nativa do Windows."""
    from deskguard.desktop import DesktopOptions, run_desktop

    defaults = DesktopOptions(
        host=settings.host,
        port=settings.port,
        width=1360,
        height=900,
    )
    options = DesktopOptions(
        host=args.host or defaults.host,
        port=args.port or defaults.port,
        title=args.title or f"DeskGuard {__version__}",
        width=args.width or defaults.width,
        height=args.height or defaults.height,
        reuse_existing=not args.no_reuse,
        browser_fallback=not args.no_browser_fallback,
        open_browser=bool(args.open_browser),
    )
    return run_desktop(settings, options)


def _command_serve(args: argparse.Namespace, settings: Settings) -> int:
    import uvicorn

    from deskguard.api.app import create_app

    host = args.host or settings.host
    port = args.port or settings.port
    app = create_app(settings)

    print("DeskGuard iniciado")
    print(f"  Interface: http://{host}:{port}/")
    print(f"  Documentação da API: http://{host}:{port}/api/docs")
    print(f"  Banco de dados: {settings.database_path}")
    print("  Pressione Ctrl+C para encerrar.\n")

    if args.open:
        import threading
        import webbrowser

        threading.Timer(
            1.5, lambda: webbrowser.open(f"http://{host}:{port}/")
        ).start()

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=settings.log_level.lower(),
        use_colors=False,
        log_config=None,
    )
    return 0


def _configure_console_encoding() -> None:
    """Força UTF-8 no console do Windows.

    Sem isso, acentos e caracteres do relatório aparecem quebrados quando a
    página de código padrão do console é cp1252.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):  # pragma: no cover - console legado
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_console_encoding()
    if argv is None:
        argv = sys.argv[1:]
    # Duplo clique no executável chega aqui sem argumentos. Nesse caso a
    # intenção do operador é abrir a interface, não receber um erro de uso:
    # assumimos o comando ``desktop`` (janela nativa). Com argumentos, a CLI
    # segue o comportamento normal.
    if not argv:
        argv = ["desktop"]
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    settings.ensure_directories()

    try:
        if args.command == "serve":
            return _command_serve(args, settings)
        if args.command == "desktop":
            return _command_desktop(args, settings)
        if args.command == "list":
            return _command_list()
        if args.command == "doctor":
            return _command_doctor(settings)
        if args.command == "run":
            return _command_run(args, settings)
        if args.command == "targets":
            return _command_targets(args)
    except DeskGuardError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover - interação manual
        print("\nInterrompido pelo usuário.")
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
