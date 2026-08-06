@echo off
setlocal

REM ============================================================
REM llama.cpp server starter for Qwen2.5 Coder 14B Instruct
REM Faster daily opencode model for RTX 5070 12 GB / 32 GB RAM
REM ============================================================

set "LLAMA_DIR=C:\tools\llama-ccp"
set "MODEL_FILE=C:\models\qwen2.5-coder-14b-instruct-q4_k_m.gguf"
set "MODEL_ALIAS=qwen2.5-coder-14b"

set "HOST=0.0.0.0"
set "PORT=8080"

REM Recommended daily coding settings
REM -ngl 999 = all layers in VRAM (14B Q4 fits ~8.5GB, leaves 3.5GB for KV cache)
REM -c 16384 = enough for opencode sessions, keeps KV cache small
REM -b 512 / -ub 256 = fast prompt processing on RTX 5070
set "GPU_LAYERS=999"
set "CTX_SIZE=20480"
set "BATCH_SIZE=512"
set "UBATCH_SIZE=256"
set "THREADS=12"

echo.
echo Starting llama.cpp server: Qwen2.5 Coder 14B
echo.
echo Llama folder: %LLAMA_DIR%
echo Model file:   %MODEL_FILE%
echo Model alias:  %MODEL_ALIAS%
echo Context size: %CTX_SIZE%
echo URL local:    http://127.0.0.1:%PORT%
echo URL network:  http://YOUR_WINDOWS_IP:%PORT%
echo API endpoint: http://YOUR_WINDOWS_IP:%PORT%/v1
echo.

if not exist "%LLAMA_DIR%\llama-server.exe" (
  echo ERROR: llama-server.exe not found in:
  echo %LLAMA_DIR%
  echo.
  pause
  exit /b 1
)

if not exist "%MODEL_FILE%" (
  echo ERROR: model file not found:
  echo %MODEL_FILE%
  echo.
  echo Download the model and save it exactly as:
  echo %MODEL_FILE%
  echo.
  pause
  exit /b 1
)

cd /d "%LLAMA_DIR%"

"%LLAMA_DIR%\llama-server.exe" ^
  -m "%MODEL_FILE%" ^
  --alias "%MODEL_ALIAS%" ^
  -ngl %GPU_LAYERS% ^
  -c %CTX_SIZE% ^
  -fa on ^
  -b %BATCH_SIZE% ^
  -ub %UBATCH_SIZE% ^
  -t %THREADS% ^
  --temp 0.2 ^
  --top-p 0.9 ^
  --repeat-penalty 1.05 ^
  --host %HOST% ^
  --port %PORT%

echo.
echo llama-server stopped.
pause
