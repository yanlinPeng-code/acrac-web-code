@echo off
echo ========================================
echo 安装 VChart 可视化组件依赖
echo ========================================
echo.

cd /d "%~dp0"

echo 正在检查 Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Node.js，请先安装 Node.js
    pause
    exit /b 1
)

echo Node.js 版本:
node --version
echo.

echo 正在检查 npm...
npm --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 npm，请先安装 npm
    pause
    exit /b 1
)

echo npm 版本:
npm --version
echo.

echo 开始安装依赖...
echo.

npm install

if errorlevel 1 (
    echo.
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo 安装完成！
echo ========================================
echo.
echo 现在可以运行以下命令启动开发服务器:
echo npm run dev
echo.
pause
