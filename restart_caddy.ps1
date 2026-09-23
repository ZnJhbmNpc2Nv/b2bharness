# Quick Caddy restart on secagent
Write-Host Перезапуск Caddy на сервере secagent... -ForegroundColor Cyan
ssh -o ConnectTimeout=10 secagent sudo systemctl restart caddy && sudo systemctl status caddy --no-pager -n 5
if ( -eq 0) {
    Write-Host [OK] Caddy успешно перезапущен! -ForegroundColor Green
} else {
    Write-Host [ERROR] Ошибка перезапуска Caddy -ForegroundColor Red
}
