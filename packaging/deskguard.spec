# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller para o executavel do DeskGuard.

Uso (a partir da raiz do projeto):

    python -m PyInstaller --noconfirm --clean packaging\\deskguard.spec

Variaveis de ambiente reconhecidas:

    DESKGUARD_BUILD_MODE=onefile     gera um unico arquivo .exe (padrao).
    DESKGUARD_BUILD_MODE=onefolder   gera uma pasta com o .exe e suas dependencias.

O executavel congelado carrega:

* a aplicacao Python (API, servicos, catalogo e coleta);
* os scripts PowerShell versionados, em ``deskguard/collectors/scripts``;
* a interface web (modelo, CSS e JavaScript), em ``deskguard/web``.

Esses tres conjuntos de arquivos sao *dados* do pacote: sem eles o executavel
sobe, mas nao coleta nem serve a interface.
"""

import os
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent
SRC = ROOT / "src"
PACKAGE = SRC / "deskguard"

BUILD_MODE = os.environ.get("DESKGUARD_BUILD_MODE", "onefile").strip().lower()
ONE_FILE = BUILD_MODE != "onefolder"

# --------------------------------------------------------------------------
# dados do pacote (nao sao modulos: precisam viajar como arquivos)
# --------------------------------------------------------------------------
datas = []

for template in sorted((PACKAGE / "web" / "templates").glob("*.html")):
    datas.append((str(template), "deskguard/web/templates"))

for css in sorted((PACKAGE / "web" / "static" / "css").glob("*.css")):
    datas.append((str(css), "deskguard/web/static/css"))

for js in sorted((PACKAGE / "web" / "static" / "js").glob("*.js")):
    datas.append((str(js), "deskguard/web/static/js"))

for script in sorted((PACKAGE / "collectors" / "scripts").glob("*.ps1")):
    datas.append((str(script), "deskguard/collectors/scripts"))

# O catalogo e montado por descoberta: o carregador usa ``pkgutil`` para
# listar os modulos do pacote ``deskguard.procedures``. Em um build
# congelado os modulos vivem no arquivo PYZ e nao aparecem no disco, entao
# os fontes do pacote tambem viajam como dados: e essa presenca no disco
# que permite a descoberta funcionar igual no modo instalado.
for module in sorted((PACKAGE / "procedures").glob("*.py")):
    datas.append((str(module), "deskguard/procedures"))

# --------------------------------------------------------------------------
# imports que o analysis estatico nao enxerga
# --------------------------------------------------------------------------
hiddenimports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "sqlalchemy.dialects.sqlite",
    "jinja2.ext",
]

# Os modulos de procedimento sao importados dinamicamente pelo carregador do
# catalogo; sem esta lista eles nao entrariam no executavel.
for module in sorted((PACKAGE / "procedures").glob("*.py")):
    if module.stem.startswith("_"):
        continue
    hiddenimports.append(f"deskguard.procedures.{module.stem}")

excludes = [
    "tkinter",
    "matplotlib",
    "numpy",
    "PIL",
    "pytest",
    "_pytest",
]

a = Analysis(
    [str(SRC / "deskguard" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

if ONE_FILE:
    # Executavel unico: o conteudo e extraido para uma pasta temporaria
    # na inicializacao.
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="DeskGuard",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(SPEC_DIR / "deskguard.ico"),
        uac_admin=False,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="DeskGuard",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(SPEC_DIR / "deskguard.ico"),
        uac_admin=False,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="DeskGuard",
    )
