@echo off
setlocal EnableExtensions
title DeskGuard

REM ==========================================================================
REM  DeskGuard - inicializacao rapida (duplo clique)
REM
REM  O que este script faz:
REM    1. localiza a raiz do projeto e o Python do ambiente virtual;
REM    2. sobe a API local do DeskGuard em segundo plano;
REM    3. abre a interface em uma JANELA NATIVA do Windows (sem navegador).
REM
REM  Para encerrar: basta fechar a janela do DeskGuard.
REM
REM  Este arquivo e mantido em ASCII puro: o cmd.exe le .bat com a pagina de
REM  codigo do sistema, e acentos podem virar caracteres invalidos.
REM ==========================================================================

set "DESKGUARD_ROOT="
set "PYTHON_EXE="
set "PYTHON_ARGS="

REM --- 1. Localiza a raiz do projeto ---------------------------------------
if defined DESKGUARD_PROJECT_DIR if exist "%DESKGUARD_PROJECT_DIR%\pyproject.toml" set "DESKGUARD_ROOT=%DESKGUARD_PROJECT_DIR%"
if not defined DESKGUARD_ROOT if exist "%~dp0..\pyproject.toml" set "DESKGUARD_ROOT=%~dp0.."
if not defined DESKGUARD_ROOT if exist "C:\Users\gustavo.fraga\Desktop\Projetos\DeskGuard\pyproject.toml" set "DESKGUARD_ROOT=C:\Users\gustavo.fraga\Desktop\Projetos\DeskGuard"

if not defined DESKGUARD_ROOT goto :sem_projeto

pushd "%DESKGUARD_ROOT%"

REM --- 2. Localiza o Python -------------------------------------------------
if exist ".venv\Scripts\pythonw.exe" set "PYTHON_EXE=.venv\Scripts\pythonw.exe"
if not defined PYTHON_EXE if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"

if defined PYTHON_EXE goto :executar

where py >nul 2>nul
if errorlevel 1 goto :sem_py
set "PYTHON_EXE=py"
set "PYTHON_ARGS=-3"
goto :executar

:sem_py
where python >nul 2>nul
if errorlevel 1 goto :sem_python
set "PYTHON_EXE=python"
goto :executar

:sem_python
echo.
echo   Python nao encontrado. Crie o ambiente virtual com:
echo     python -m venv .venv
echo     .venv\Scripts\python.exe -m pip install -e ".[dev,desktop]"
echo.
pause
popd
endlocal
exit /b 1

:sem_projeto
echo.
echo   DeskGuard nao encontrou a pasta do projeto.
echo.
echo   Edite a linha "set DESKGUARD_PROJECT_DIR=" no inicio deste arquivo
echo   apontando para a pasta que contem o pyproject.toml.
echo.
pause
endlocal
exit /b 1

:executar
REM --- 3. Abre a janela nativa ---------------------------------------------
set "DESKGUARD_LOG=%LOCALAPPDATA%\DeskGuard\desktop.log"
if not exist "%LOCALAPPDATA%\DeskGuard" mkdir "%LOCALAPPDATA%\DeskGuard" >nul 2>nul

echo DeskGuard iniciando a partir de "%DESKGUARD_ROOT%" ...
start "DeskGuard" "%PYTHON_EXE%" %PYTHON_ARGS% -m deskguard desktop >> "%DESKGUARD_LOG%" 2>&1

popd
endlocal
exit /b 0
