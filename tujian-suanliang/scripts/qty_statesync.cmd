@echo off
rem qty_statesync launcher (ASCII only on purpose; untested on real Windows)
setlocal
set "HERE=%~dp0"
set "PY=%PYTHON%"
if not defined PY set "PY=python"
"%PY%" "%HERE%qty_statesync.py" %*
