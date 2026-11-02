@echo off
rem tujian-suanliang 统一入口（Windows 无 Git Bash 时兜底）。
rem 等价于 macOS/Linux 的 scripts/run_qty.sh；脚本会继续走 python 主入口。
setlocal
set "SKILL_DIR=%~dp0.."
set "FIRST=%~1"
if "%FIRST%"=="advanced" goto :pipeline
if "%FIRST%"=="pipeline" goto :pipeline
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SKILL_DIR%\scripts\qty_core.py" %*
  exit /b %errorlevel%
)
where python >nul 2>nul
if %errorlevel%==0 (
  python "%SKILL_DIR%\scripts\qty_core.py" %*
  exit /b %errorlevel%
)
echo [run_qty] 未找到 Python 3；请安装 Python 并加入 PATH 1>&2
exit /b 127

:pipeline
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SKILL_DIR%\scripts\cad_quantity_pipeline.py" %*
  exit /b %errorlevel%
)
where python >nul 2>nul
if %errorlevel%==0 (
  python "%SKILL_DIR%\scripts\cad_quantity_pipeline.py" %*
  exit /b %errorlevel%
)
echo [run_qty] 未找到 Python 3；请安装 Python 并加入 PATH 1>&2
exit /b 127
