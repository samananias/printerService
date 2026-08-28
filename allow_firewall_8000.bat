@echo off
REM ============================================================
REM  Phase 1 helper: allow inbound TCP port 8000 (private networks
REM  only) so the phone can reach the service. README Sections 7-8.
REM
REM  HOW TO USE: right-click this file -> "Run as administrator".
REM  The admin prompt is required because firewall rules are
REM  machine-wide security settings, not per-user preferences.
REM ============================================================

netsh advfirewall firewall add rule ^
  name="Printer Service (TCP 8000)" ^
  dir=in action=allow protocol=TCP localport=8000 profile=private

echo.
echo Done. Rule "Printer Service (TCP 8000)" added for private networks.
echo Verify in: Windows Security ^> Firewall ^> Advanced settings ^> Inbound Rules
pause
