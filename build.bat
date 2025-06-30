@echo off
echo Building content-create-agent with PyInstaller...

:: Clean previous build if exists
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

:: Run PyInstaller with the spec file without confirmation prompts
pyinstaller --noconfirm content-create-agent.spec

echo Build completed successfully!
echo The executable is located at: dist\content-create-agent\content-create-agent.exe

pause