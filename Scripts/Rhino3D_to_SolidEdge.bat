@echo off
setlocal EnableExtensions
rem Stable legacy entry point for existing desktop shortcuts and callers.
set "TARGET=%~dp0Inventaur_Rhino3D_to_SolidEdge.bat"
if not exist "%TARGET%" (echo ERROR: Required workflow launcher is missing: "%TARGET%" & if not "%CAD_WORKFLOW_NO_PAUSE%"=="1" pause & exit /b 2)
call "%TARGET%" %*
set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%
