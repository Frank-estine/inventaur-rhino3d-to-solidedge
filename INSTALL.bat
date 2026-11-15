@echo off
setlocal EnableExtensions
title Inventaur Inc. - Rhino3D to Solid Edge Bootstrap
set "INSTALLER=%~dp0Inventaur_Install.ps1"
if not exist "%INSTALLER%" (echo ERROR: Inventaur_Install.ps1 is missing. Extract the complete package. & if not "%CAD_WORKFLOW_NO_PAUSE%"=="1" pause & exit /b 2)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%INSTALLER%" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (echo. & echo INSTALLATION FAILED. Exit code: %EXIT_CODE% & if not "%CAD_WORKFLOW_NO_PAUSE%"=="1" pause & exit /b %EXIT_CODE%)
echo.
echo BOOTSTRAP INSTALLED AND VERIFIED.
echo Restart Rhino before running the conversion workflow.
if not "%CAD_WORKFLOW_NO_PAUSE%"=="1" pause
exit /b 0
