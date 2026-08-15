@echo off
REM run_pipeline.bat -- wraps ims_pipeline.py with a fixed BASE_DIR/OUTPUT_ROOT
REM so you only ever type the subfolder name.
REM
REM Usage:
REM   run_pipeline.bat set2_data 4
REM   (subfolder name, then channel count -- channel count defaults to 4)

set BASE_DIR=%~dp0..\data
set OUTPUT_ROOT=%~dp0..\outputs

if "%~1"=="" (
    echo Usage: run_pipeline.bat ^<subfolder e.g. set2_data^> ^[n-channels, default 4^]
    exit /b 1
)

set DATA_SUBDIR=%~1
set N_CHANNELS=%~2
if "%N_CHANNELS%"=="" set N_CHANNELS=4

python "%~dp0ims_pipeline.py" --data-dir "%DATA_SUBDIR%" --base-dir "%BASE_DIR%" --out-dir "%OUTPUT_ROOT%" --n-channels %N_CHANNELS%
