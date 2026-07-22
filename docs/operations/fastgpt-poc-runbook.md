# FastGPT 有界 PoC 运行记录

## 范围

该本地 PoC 只使用 `docs/fixtures/fastgpt-poc/employee-leave-policy.md`。FastGPT 是可替换的 RAG 提供方，不是 SmartCS 的产品入口或业务事实来源。员工身份、租户授权、审计事件、转人工记录和应用业务状态仍由 SmartCS 负责。

## 存储位置

- 部署目录：`D:\DevData\smartcs-fastgpt-poc\deployment`
- Docker Desktop 程序文件与磁盘镜像必须保留在 D 盘。
- 本地凭据：仓库根目录 `.env.fastgpt-poc`，该文件已被 Git 忽略。

## 预检要求

记录 Docker Desktop、Docker Engine、Compose 版本，部署前 D 盘剩余空间，以及 Docker 磁盘镜像位置。不要记录密码、API Key、App ID 或私有 IP。

## 预检结果（2026-07-17）

**状态：通过。**

- Docker Desktop 4.82.0 正常运行，Engine 29.6.1，Compose v5.3.0。
- `desktop-linux` 使用 WSL 2 后端；`docker version`、`docker compose version`、`docker info`、`docker ps` 均执行成功。
- 安装后 D 盘剩余 75.89 GiB，满足此有界 PoC。
- Docker 磁盘镜像位于 D 盘。
- 当时尚未拉取 FastGPT 或 PoC 镜像。
- `D:\2026.07.09\docker` 下存在从旧电脑复制的 Docker Desktop 4.79.0 和 7.15 GiB `docker_data.vhdx`；不运行旧二进制，也不直接挂载旧数据盘。

## 部署结果（2026-07-17）

**状态：通过。**

- Compose 来源：FastGPT 官方 v4.15 PgVector 部署方案。
- 核心镜像版本：Mongo 5.0.32、PgVector 0.8.0-pg15、FastGPT 4.15.1、Redis 7.2、AIProxy 0.6.5；精确镜像记录保留在部署目录的 Compose 文件中。
- `http://127.0.0.1:3000` 返回 HTTP 200。
- 必需容器均在运行，带健康检查的组件状态正常；观察窗口内 FastGPT 与 AIProxy 重启次数为 0。
- 生成的凭据只保存在 `D:\DevData\smartcs-fastgpt-poc\deployment`。
- 部署后 D 盘剩余 67.23 GiB。

该 PoC 已完成框架可用性验证，但 SmartCS 最终保留自有 Python 后端、治理和权限主线，不把 FastGPT 配置本身作为核心技术成果。

## 停止服务

在部署目录执行 `docker compose down`。在确认不再需要 PoC 数据和验收证据前，不使用 `-v`。
