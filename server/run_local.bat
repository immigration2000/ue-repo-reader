@echo off
rem Run the ue-repo-reader MCP server on this Windows PC (needs Python 3.10+ and Git for Windows).
rem Expose it with a tunnel, e.g.:  cloudflared tunnel --url http://localhost:8000
cd /d "%~dp0\.."
python -m pip install --quiet -r server\requirements.txt || goto :error
if "%UE_READER_SECRET%"=="" (
  for /f %%i in ('python -c "import secrets; print(secrets.token_urlsafe(24))"') do set UE_READER_SECRET=%%i
)
set PORT=8000
set UE_READER_DATA=%LOCALAPPDATA%\ue-repo-reader
set UE_READER_WORKERS=4
echo.
echo MCP endpoint (local): http://localhost:8000/%UE_READER_SECRET%/mcp
echo With a tunnel use:    https://^<tunnel-host^>/%UE_READER_SECRET%/mcp
echo.
python server\server.py
goto :eof
:error
echo Failed to install requirements.
pause
