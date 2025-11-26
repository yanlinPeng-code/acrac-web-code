@echo off
REM 评测平台部署脚本 (Windows版本)
REM 端口: 5188

setlocal enabledelayedexpansion

echo ================================================
echo 评测平台部署脚本
echo ================================================
echo.

REM 检查Docker是否安装
docker --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Docker未安装，请先安装Docker Desktop
    pause
    exit /b 1
)

REM 检查docker-compose是否安装
docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo [错误] docker-compose未安装，请先安装docker-compose
    pause
    exit /b 1
)

REM 停止并移除旧容器
echo [信息] 停止旧容器...
docker-compose down

REM 询问是否清理旧镜像
set /p CLEAN_IMAGES="是否清理旧镜像? (y/N): "
if /i "%CLEAN_IMAGES%"=="y" (
    echo [信息] 清理旧镜像...
    docker-compose down --rmi all
)

REM 构建镜像
echo [信息] 构建Docker镜像...
docker-compose build --no-cache
if errorlevel 1 (
    echo [错误] 镜像构建失败
    pause
    exit /b 1
)

REM 启动服务
echo [信息] 启动服务...
docker-compose up -d
if errorlevel 1 (
    echo [错误] 服务启动失败
    pause
    exit /b 1
)

REM 等待服务启动
echo [信息] 等待服务启动...
timeout /t 10 /nobreak >nul

REM 检查服务状态
echo [信息] 检查服务状态...
docker-compose ps

REM 检查后端健康状态
echo [信息] 检查后端健康状态...
set BACKEND_READY=0
for /l %%i in (1,1,10) do (
    curl -f http://localhost:8000/health >nul 2>&1
    if not errorlevel 1 (
        echo [成功] 后端服务启动成功
        set BACKEND_READY=1
        goto :check_frontend
    )
    echo 等待后端启动... (%%i/10)
    timeout /t 3 /nobreak >nul
)

:check_frontend
if %BACKEND_READY%==0 (
    echo [错误] 后端服务启动失败
    docker-compose logs backend
    pause
    exit /b 1
)

REM 检查前端健康状态
echo [信息] 检查前端健康状态...
set FRONTEND_READY=0
for /l %%i in (1,1,10) do (
    curl -f http://localhost:5188 >nul 2>&1
    if not errorlevel 1 (
        echo [成功] 前端服务启动成功
        set FRONTEND_READY=1
        goto :deploy_complete
    )
    echo 等待前端启动... (%%i/10)
    timeout /t 3 /nobreak >nul
)

:deploy_complete
if %FRONTEND_READY%==0 (
    echo [错误] 前端服务启动失败
    docker-compose logs frontend
    pause
    exit /b 1
)

echo.
echo ================================================
echo [成功] 部署完成!
echo ================================================
echo.
echo 访问地址:
echo   前端: http://localhost:5188
echo   后端API: http://localhost:8000
echo   后端文档: http://localhost:8000/docs
echo.
echo 常用命令:
echo   查看日志: docker-compose logs -f
echo   查看后端日志: docker-compose logs -f backend
echo   查看前端日志: docker-compose logs -f frontend
echo   停止服务: docker-compose down
echo   重启服务: docker-compose restart
echo.
pause
