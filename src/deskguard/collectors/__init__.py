"""Camada de coleta: único ponto de contato com o sistema operacional."""

from deskguard.collectors.base import Collector, ProbeContext, run_collectors
from deskguard.collectors.powershell import PowerShellOutcome, PowerShellRunner

__all__ = [
    "Collector",
    "PowerShellOutcome",
    "PowerShellRunner",
    "ProbeContext",
    "run_collectors",
]
