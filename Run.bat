@echo off
setlocal
cd /d "%~dp0"
call "%USERPROFILE%\miniconda3\condabin\conda.bat" activate UEPluginAutoPacker
if errorlevel 1 exit /b 1
if not "%~1"=="" goto cli
if not exist "%CONDA_PREFIX%\pythonw.exe" exit /b 1
start "" "%CONDA_PREFIX%\pythonw.exe" "%~dp0Main.py"
exit /b %ERRORLEVEL%

:cli
python "%~dp0Main.py" %*
exit /b %ERRORLEVEL%
