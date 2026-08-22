@echo off
chcp 65001 >nul
echo ============================================
echo   下片神器 打包脚本 (PyInstaller onedir)
echo ============================================

set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe
if exist "venv\Scripts\python.exe" set PY=venv\Scripts\python.exe

echo [1/4] 安装依赖...
%PY% -m pip install -r requirements.txt -q

echo [2/4] 检查 ffmpeg...
if not exist "ffmpeg\ffmpeg.exe" (
    echo [!] 未找到 ffmpeg\ffmpeg.exe，请先下载 ffmpeg (https://www.gyan.dev/ffmpeg/builds/) 放入 ffmpeg\ 目录
    exit /b 1
)

echo [3/4] 清理旧产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/4] PyInstaller 打包...
set ICON_OPT=
if exist "resources\app.ico" set ICON_OPT=--icon "resources\app.ico"
%PY% -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name XpsqDownloader ^
  --collect-all trafilatura ^
  --add-data "ffmpeg\ffmpeg.exe;ffmpeg" ^
  %ICON_OPT% ^
  main.py

echo 复制 ffmpeg 到产物目录...
if exist "dist\XpsqDownloader\_internal\ffmpeg" (
    copy /y "ffmpeg\ffmpeg.exe" "dist\XpsqDownloader\_internal\ffmpeg\" >nul
)

echo.
echo 完成！运行 dist\XpsqDownloader\XpsqDownloader.exe
pause
