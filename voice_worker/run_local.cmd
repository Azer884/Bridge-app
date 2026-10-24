@echo off
rem Starts the voice worker in development mode. First time: python -m venv .venv-voice
rem then .venv-voice\Scripts\python -m pip install -r voice_worker\requirements.txt and fill .env.local
cd /d "%~dp0.."
.venv-voice\Scripts\python -m voice_worker.check
if errorlevel 1 (
  echo Fix the problems above, then run this again.
  pause
  exit /b 1
)
.venv-voice\Scripts\python -m voice_worker.agent start
