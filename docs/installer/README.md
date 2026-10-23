# Instalador do DeskGuard

## Opção 1: Inno Setup (Recomendado para Windows)

1. Baixe e instale o [Inno Setup](https://jrsoftware.org/isinfo.php)
2. Gere o executável: `pyinstaller packaging/deskguard.spec --clean --noconfirm`
3. Compile o instalador: abra `scripts/installer/DeskGuard.iss` no Inno Setup Compiler e clique em Compile
4. O instalador será gerado em `Output/DeskGuard-Setup-0.2.0.exe`

O instalador cria atalhos na Área de Trabalho e no Menu Iniciar.

## Opção 2: GitHub Actions (Automático)

Ao criar uma tag `v*` (ex: `v0.2.0`), o workflow `.github/workflows/build.yml` compila automaticamente o executável e o instalador, disponibilizando-os na aba Releases.

## Opção 3: Apenas o executável

Baixe `DeskGuard.exe` diretamente dos Releases ou da pasta `dist/` após o build. Não precisa de Python instalado.
