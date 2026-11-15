@echo off
setlocal EnableExtensions
title Inventaur Inc. - Rhino3D to Solid Edge
for %%I in ("%~dp0.") do set "SCRIPT_DIR=%%~fI"
for %%I in ("%SCRIPT_DIR%\..") do set "WORKFLOW_ROOT=%%~fI"
set "ENTRY_SCRIPT=%SCRIPT_DIR%\inventaur_rhino3d_to_solidedge.py"
set "MCP_ROOT=%SCRIPT_DIR%\SOLIDEDGE-MCP"
set "RUNTIME=%MCP_ROOT%\runtime\win-x64"
set "CONTROL_EXE=%RUNTIME%\control\solidedge-mcp.exe"
set "EVENT_EXE=%RUNTIME%\events\solidedge-event-mcp.exe"
set "PYTHON_EXE=%WORKFLOW_ROOT%\.venv\Scripts\python.exe"
if not exist "%ENTRY_SCRIPT%" (echo ERROR: Workflow entry point is missing: "%ENTRY_SCRIPT%" & goto :failed)
for %%F in (inventaur_bridge_client.py inventaur_bridge_daemon.py inventaur_process_policy.py) do if not exist "%MCP_ROOT%\%%F" (echo ERROR: Solid Edge bridge source is missing: "%MCP_ROOT%\%%F" & goto :failed)
for %%F in ("%CONTROL_EXE%" "%RUNTIME%\control\coreclr.dll" "%RUNTIME%\control\hostfxr.dll" "%RUNTIME%\control\hostpolicy.dll" "%RUNTIME%\control\System.Private.CoreLib.dll" "%EVENT_EXE%" "%RUNTIME%\events\coreclr.dll" "%RUNTIME%\events\hostfxr.dll" "%RUNTIME%\events\hostpolicy.dll" "%RUNTIME%\events\System.Private.CoreLib.dll") do if not exist "%%~F" (echo ERROR: Bundled Solid Edge MCP runtime file missing: "%%~F" & echo Re-extract the complete package or run INSTALL.bat again. & goto :failed)
if not exist "%PYTHON_EXE%" (echo ERROR: Workflow Python environment is not installed. & echo Run INSTALL.bat first. & goto :failed)
set "CAD_WORKFLOW_MCP_ROOT=%MCP_ROOT%"
set "PYTHONPATH=%MCP_ROOT%;%PYTHONPATH%"
set "PYTHONUTF8=1"
cd /d "%SCRIPT_DIR%"
if errorlevel 1 (echo ERROR: Cannot enter workflow Scripts directory: "%SCRIPT_DIR%" & goto :failed)
"%PYTHON_EXE%" "%ENTRY_SCRIPT%" %*
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" (echo. & echo WORKFLOW COMPLETED SUCCESSFULLY.) else (echo. & echo WORKFLOW FAILED. Exit code: %EXIT_CODE% & echo Review the error above and Logs in the generated Desktop output folder.)
if "%CAD_WORKFLOW_NO_PAUSE%"=="1" goto :return
pause
:return
exit /b %EXIT_CODE%
:failed
set "EXIT_CODE=2"
if not "%CAD_WORKFLOW_NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
