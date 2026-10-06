@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Installation de Jarvis ===
where python >nul 2>nul || (echo Python introuvable. Installe Python 3.11 ou 3.12 depuis python.org en cochant "Add to PATH". & pause & exit /b 1)
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || (echo L'installation a echoue. & pause & exit /b 1)
where ffmpeg >nul 2>nul || (echo Installation de FFmpeg pour le montage... & winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements)
if not exist .env copy .env.example .env >nul
echo.
echo Termine. Ouvre le fichier .env, colle ta cle ANTHROPIC_API_KEY, puis lance lancer.bat
pause
