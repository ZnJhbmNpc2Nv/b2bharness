@echo off
chcp 65001 >nul
echo [Caddy] Restarting Caddy on secagent...
ssh -o ConnectTimeout=10 secagent "sudo systemctl restart caddy && sudo systemctl is-active caddy"
if %ERRORLEVEL% equ 0 (
    echo [Caddy] [OK] Caddy restarted successfully!
) else (
    echo [Caddy] [ERROR] Failed to restart Caddy.
)
pause
