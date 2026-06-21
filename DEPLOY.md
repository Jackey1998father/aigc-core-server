# AIGC Core Server 部署指南（阿里云 Docker 部署）

## 快速预览：本地开发 vs 服务器部署

| 场景 | 使用的配置 | 说明 |
|------|-----------|------|
| **本地开发** | `.env` 文件 | pydantic-settings 自动读取，方便调试 |
| **Docker 部署** | `docker-compose.yml` 中的 `env_file: .env` | 由 Docker 将环境变量注入容器，`.env` **不打包进镜像** |

> 🔑 **核心区别**：`.env` 是本地开发用的，服务器部署时在服务器上单独创建 `.env` 文件，通过 docker-compose 的 `env_file` 注入到容器中。

---

## 目录结构（部署所需文件）

```
aigc-core-server/
├── app/                      # 应用代码
├── Dockerfile                # 镜像构建文件
├── docker-compose.yml        # 容器编排配置
├── requirements.txt          # Python 依赖
├── .dockerignore             # 构建时忽略的文件
│
├── .env.production           # ⭐ 生产环境配置示例（需复制为 .env）
├── .env                      # 本地开发配置（不上传服务器）
│
└── nginx/                    # Nginx 反向代理配置（可选）
    ├── nginx.conf
    ├── conf.d/
    │   └── default.conf
    └── cert/                 # SSL 证书存放目录（如有 HTTPS）
```

---

## 方式一：Docker 部署（推荐生产环境）

### 1. 服务器环境准备（阿里云 ECS）

#### 1.1 安装 Docker & Docker Compose

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | bash

# 启动 Docker 并设置开机自启
systemctl start docker
systemctl enable docker

# 验证安装
docker --version
docker compose version
```

#### 1.2 阿里云安全组配置

在阿里云控制台 → 云服务器 ECS → 安全组 → 配置规则：

| 协议类型 | 端口范围 | 授权对象 | 说明 |
|---------|---------|---------|------|
| TCP     | 22      | 0.0.0.0/0 | SSH（建议限制为你的 IP） |
| TCP     | 8000    | 0.0.0.0/0 | 应用端口（如用 Nginx 可不开） |
| TCP     | 80      | 0.0.0.0/0 | HTTP |
| TCP     | 443     | 0.0.0.0/0 | HTTPS |

#### 1.3 服务器防火墙（如启用）

```bash
# 开放端口
firewall-cmd --permanent --add-port=8000/tcp
firewall-cmd --permanent --add-port=80/tcp
firewall-cmd --permanent --add-port=443/tcp
firewall-cmd --reload
```

---

### 2. 上传代码到服务器

#### 方式 A：使用 Git（推荐，便于后续更新）

```bash
# 在阿里云服务器上
cd /opt
git clone <你的代码仓库地址> aigc-core-server
cd aigc-core-server
```

#### 方式 B：打包上传

```bash
# ===== 本地执行 =====
# 在项目根目录打包（排除不需要的文件）
zip -r aigc-core-server.zip . \
    -x "*.git*" -x "__pycache__/*" -x "*.pyc" \
    -x "venv/*" -x ".idea/*" -x ".vscode/*" \
    -x "logs/*" -x "data/*"

# 上传到服务器
scp aigc-core-server.zip root@<服务器IP>:/opt/

# ===== 服务器上执行 =====
cd /opt
unzip aigc-core-server.zip
cd aigc-core-server
```

---

### 3. 配置生产环境变量 ⭐ 关键步骤

```bash
cd /opt/aigc-core-server

# 1. 从示例文件复制
cp .env.production .env

# 2. 编辑配置（务必修改 API_SECRET_TOKEN 和 SECRET_KEY）
vim .env
```

**`.env` 文件关键配置项说明：**

```dotenv
# ===== 必须修改 =====
DEBUG=false                                        # 生产环境务必关闭
API_SECRET_TOKEN=你的32位以上随机字符串              # 接口鉴权 Token
SECRET_KEY=你的随机密钥                              # 内部签名密钥

# ===== 按需配置 =====
CORS_ORIGINS=*                                     # 生产环境建议指定具体域名
# 例如：CORS_ORIGINS=https://your-domain.com
```

**生成随机密钥的命令：**
```bash
# 生成 API_SECRET_TOKEN
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 生成 SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

### 4. 启动服务

#### 方案 A：仅启动应用服务（最简）

如果你不需要 Nginx 反向代理，先编辑 `docker-compose.yml`，**注释掉 nginx 服务部分**，然后：

```bash
cd /opt/aigc-core-server

# 构建并启动
docker compose up -d --build

# 查看运行状态
docker compose ps

# 查看日志
docker compose logs -f aigc-server
```

访问验证：`http://<服务器IP>:8000/docs`

#### 方案 B：应用 + Nginx 反向代理（推荐生产）

使用默认的 `docker-compose.yml`（包含 nginx 服务）：

```bash
cd /opt/aigc-core-server

# 如需启用 HTTPS，先将证书放到 nginx/cert/ 目录
# server.crt 和 server.key

# 如暂时不需要 HTTPS，先编辑 nginx/conf.d/default.conf
# 启用 HTTP 配置，注释掉 HTTPS server 块

# 构建并启动
docker compose up -d --build

# 验证
curl http://localhost/api/v1/health
```

---

### 5. 验证部署

```bash
# 检查容器状态
docker compose ps

# 查看应用日志
docker compose logs -f aigc-server

# 查看 Nginx 日志
docker compose logs -f nginx

# 健康检查
curl http://localhost:8000/docs

# 测试接口（如启用了 API_SECRET_TOKEN）
curl -X POST http://localhost:8000/api/v1/siliconflow/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <你的API_SECRET_TOKEN>" \
  -d '{"model": "Pro/zai-org/GLM-5.1", "messages": [{"role": "user", "content": "你好"}]}'
```

---

### 6. 常用维护命令

```bash
# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f aigc-server      # 实时日志
docker compose logs --tail=100 aigc-server  # 最近100行

# 重启服务
docker compose restart aigc-server

# 停止服务
docker compose stop

# 停止并移除容器
docker compose down

# 重新构建并启动（代码更新后）
docker compose up -d --build

# 进入容器调试
docker exec -it aigc-core-server bash

# 查看资源使用
docker stats
```

---

### 7. 更新代码流程

```bash
cd /opt/aigc-core-server

# 拉取最新代码
git pull

# 重新构建并启动
docker compose up -d --build

# 验证
docker compose ps
docker compose logs -f --tail=50 aigc-server
```

---

## 方式二：直接部署（无 Docker，适合测试）

### 1. 安装 Python 环境

```bash
apt update
apt install -y python3 python3-pip python3-venv
```

### 2. 创建虚拟环境并安装依赖

```bash
cd /opt/aigc-core-server

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.production .env
vim .env  # 修改配置
```

### 4. 使用 systemd 管理服务

```bash
# 创建服务文件
cat > /etc/systemd/system/aigc-server.service << 'EOF'
[Unit]
Description=AIGC Core Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aigc-core-server
Environment="PATH=/opt/aigc-core-server/venv/bin"
ExecStart=/opt/aigc-core-server/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
systemctl daemon-reload
systemctl enable aigc-server
systemctl start aigc-server

# 查看状态
systemctl status aigc-server
journalctl -u aigc-server -f
```

---

## 配置域名与 HTTPS（可选）

### 1. 域名解析

在阿里云 DNS 控制台添加域名解析到服务器 IP。

### 2. 申请免费 SSL 证书（Let's Encrypt）

```bash
# 安装 certbot
apt install -y certbot

# 申请证书（需先停止占用 80 端口的服务）
certbot certonly --standalone -d your-domain.com

# 证书路径：
# /etc/letsencrypt/live/your-domain.com/fullchain.pem
# /etc/letsencrypt/live/your-domain.com/privkey.pem

# 将证书复制到 nginx/cert/ 目录
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /opt/aigc-core-server/nginx/cert/server.crt
cp /etc/letsencrypt/live/your-domain.com/privkey.pem /opt/aigc-core-server/nginx/cert/server.key

# 自动续期（Let's Encrypt 证书 90 天有效）
certbot renew --dry-run
```

### 3. 启用 Nginx HTTPS 配置

编辑 `nginx/conf.d/default.conf`，启用 HTTPS server 块，修改 `server_name` 为你的域名，然后重启：

```bash
cd /opt/aigc-core-server
docker compose restart nginx
```

---

## 配置文件详解

### `.env` vs `docker-compose.yml` 的关系

| 配置方式 | 说明 |
|---------|------|
| `config.py` 中的 `env_file=".env"` | 本地开发时，pydantic-settings 自动读取 `.env` |
| `docker-compose.yml` 中的 `env_file: .env` | Docker 部署时，Compose 将 `.env` 的内容注入容器环境变量 |
| `.dockerignore` 中的 `.env` | `.env` **不打包进镜像**，安全且便于在不同环境独立配置 |

### 为什么 `.env` 不进镜像？

1. **安全**：密钥不应该打包进镜像文件
2. **灵活**：不同环境（开发/测试/生产）用不同配置
3. **易于维护**：修改配置无需重新构建镜像

---

## 故障排查

### 问题 1：容器启动失败

```bash
# 查看完整日志
docker compose logs aigc-server

# 常见原因：
# - .env 文件不存在或格式错误
# - 端口被占用：netstat -tlnp | grep 8000
# - 权限问题：日志目录不存在或无写入权限
```

### 问题 2：无法访问 API

```bash
# 1. 检查容器是否运行
docker compose ps

# 2. 检查端口监听
netstat -tlnp | grep 8000

# 3. 本地测试（在服务器上）
curl http://localhost:8000/docs

# 4. 检查防火墙和安全组
# - 阿里云安全组是否放行端口
# - 服务器防火墙是否放行端口
```

### 问题 3：Nginx 502 Bad Gateway

这通常表示 Nginx 无法连接到后端应用服务：

```bash
# 检查 aigc-server 容器是否健康
docker compose ps

# 检查容器间网络连通性
docker exec aigc-nginx ping aigc-server  # 或
docker exec aigc-nginx wget -qO- http://aigc-server:8000/docs

# 重启服务
docker compose restart
```

### 问题 4：流式响应（SSE）不工作

确保 Nginx 配置中已添加：
```nginx
proxy_http_version 1.1;
proxy_set_header Connection "";
proxy_buffering off;
proxy_cache off;
```

---

## 安全建议清单

- [ ] `DEBUG=false`
- [ ] 设置强 `API_SECRET_TOKEN`
- [ ] 设置唯一的 `SECRET_KEY`
- [ ] CORS 限制为实际使用的域名（非 `*`）
- [ ] 使用 HTTPS
- [ ] 阿里云安全组限制 SSH 来源 IP
- [ ] 定期更新 Docker 镜像和系统包
- [ ] 监控日志，关注异常请求
- [ ] 备份配置文件（`.env`）
