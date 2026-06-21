# AIGC Core Server 部署指南

## 方式一：Docker 部署（推荐）

### 1. 在阿里云服务器上安装 Docker

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | bash

# 启动 Docker
systemctl start docker
systemctl enable docker
```

### 2. 上传代码到服务器

```bash
# 在本地项目根目录打包
zip -r aigc-core-server.zip . -x "*.git*" -x "__pycache__/*"

# 上传到阿里云
scp aigc-core-server.zip root@你的服务器IP:/root/
```

### 3. 在服务器上解压并启动

```bash
# 解压
cd /root
unzip aigc-core-server.zip
cd aigc-core-server

# 构建并启动
docker-compose up -d

# 查看日志
docker logs -f aigc-core-server
```

### 4. 验证部署

```bash
curl http://localhost:8000/api/v1/health
```

---

## 方式二：直接部署（无 Docker）

### 1. 安装 Python 环境

```bash
# 安装 Python 3.10+
apt update
apt install -y python3 python3-pip
```

### 2. 安装依赖

```bash
cd /root/aigc-core-server
pip install -r requirements.txt
pip install requests
```

### 3. 启动服务

```bash
# 直接启动（前台）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 或后台运行
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
```

### 4. 设置开机自启（systemd）

```bash
# 创建服务文件
cat > /etc/systemd/system/aigc-server.service << EOF
[Unit]
Description=AIGC Core Server
After=network.target

[Service]
User=root
WorkingDirectory=/root/aigc-core-server
ExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 启用服务
systemctl daemon-reload
systemctl enable aigc-server
systemctl start aigc-server
```

---

## 配置域名（可选）

1. 在阿里云 DNS 控制台添加域名解析到服务器 IP
2. 使用 Nginx 反向代理：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

3. 配置 SSL 证书（推荐 Let's Encrypt）

---

## 防火墙配置

```bash
# 开放 8000 端口
firewall-cmd --permanent --add-port=8000/tcp
firewall-cmd --reload

# 或使用阿里云安全组
# 在云服务器控制台 → 安全组 → 添加规则 → 端口 8000
```

---

## 常用命令

```bash
# Docker 部署时
docker-compose logs -f      # 查看日志
docker-compose restart     # 重启服务
docker-compose down         # 停止服务
docker-compose build        # 重新构建

# 直接部署时
systemctl restart aigc-server   # 重启
systemctl status aigc-server    # 查看状态
journalctl -u aigc-server -f    # 查看日志
```
