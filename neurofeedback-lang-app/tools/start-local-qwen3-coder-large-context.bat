@echo off
setlocal

REM ============================================================
REM llama.cpp server starter for local Qwen3 Coder model
REM Large context version for opencode requests > 8192 tokens
REM ============================================================

set "LLAMA_DIR=C:\tools\llama-ccp"
set "MODEL_FILE=C:\models\Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf"
set "MODEL_ALIAS=qwen3-coder-30b-a3b"

set "HOST=0.0.0.0"
set "PORT=8080"

REM Large context settings
REM -ngl 999 = offload all layers that fit in VRAM (auto-caps to model max)
REM -c 16384 = enough for guardrails + task prompt; was 32768 but KV cache was killing PP speed
REM -b/-ub 512/256 = fast prompt processing on RTX 5070
set "GPU_LAYERS=999"
set "CTX_SIZE=24576"
set "BATCH_SIZE=512"
set "UBATCH_SIZE=256"
set "THREADS=12"

echo.
echo Starting llama.cpp server with LARGE CONTEXT...
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
  echo Edit this BAT file and correct MODEL_FILE.
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
