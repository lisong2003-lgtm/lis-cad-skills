@echo off
rem steel_tonnage launcher (ASCII only on purpose; untested on real Windows)
setlocal
set "HERE=%~dp0"
set "PY=%PYTHON%"
if not defined PY set "PY=%CODEX_PYTHON%"
if not defined PY set "PY=python"
"%PY%" "%HERE%steel_tonnage.py" %*
