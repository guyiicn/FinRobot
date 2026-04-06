# FinRobot Docker 部署指南

## 📋 前置要求

- Docker 20.10+
- Docker Compose 2.0+

## 🚀 快速开始

### 1. 配置 API Keys

```bash
# 复制配置模板
cp finrobot_equity/core/config/config.ini.template finrobot_equity/core/config/config.ini

# 编辑配置文件，填入你的 API Keys
nano finrobot_equity/core/config/config.ini
```

配置示例：
```ini
[API_KEYS]
fmp_api_key = YOUR_FMP_API_KEY
openai_api_key = YOUR_OPENAI_API_KEY
adanos_api_key = YOUR_ADANOS_API_KEY  # 可选
```

### 2. 构建并启动

```bash
# 使用 Docker Compose（推荐）
docker-compose up -d

# 或者使用 Docker 直接运行
docker build -t finrobot:latest .
docker run -d \
  --name finrobot \
  -p 8001:8001 \
  -v $(pwd)/finrobot_equity/core/config:/app/finrobot_equity/core/config:ro \
  -v finrobot_data:/app/finrobot_equity/web_app/data \
  -v finrobot_output:/app/output \
  finrobot:latest
```

### 3. 访问应用

打开浏览器访问: http://localhost:8001

## 📝 常用命令

### Docker Compose 命令

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f finrobot

# 停止所有服务
docker-compose down

# 停止并删除数据卷（⚠️ 会删除所有数据）
docker-compose down -v

# 重启服务
docker-compose restart finrobot

# 查看服务状态
docker-compose ps

# 进入容器
docker-compose exec finrobot bash
```

### Docker 命令

```bash
# 查看容器日志
docker logs -f finrobot_app

# 停止容器
docker stop finrobot_app

# 启动容器
docker start finrobot_app

# 重启容器
docker restart finrobot_app

# 删除容器
docker rm finrobot_app

# 删除镜像
docker rmi finrobot:latest
```

## 🔧 配置说明

### 端口配置

修改 `docker-compose.yml` 中的端口映射：
```yaml
ports:
  - "8080:8001"  # 将外部端口改为 8080
```

或者通过环境变量：
```bash
WEB_PORT=8080 docker-compose up -d
```

### 数据持久化

数据存储在 Docker Volume 中：

| Volume | 用途 |
|--------|------|
| `finrobot_data` | 应用数据和数据库 |
| `finrobot_output` | 生成的报告输出 |
| `finrobot_logs` | 日志文件 |

查看 Volume：
```bash
docker volume ls | grep finrobot

# 查看详细内容
docker volume inspect finrobot_data
```

备份 Volume：
```bash
docker run --rm -v finrobot_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/finrobot_data_backup.tar.gz /data
```

### API Keys 管理

#### 方式 1: Config 文件（推荐）

通过 Volume 挂载：
```yaml
volumes:
  - ./finrobot_equity/core/config:/app/finrobot_equity/core/config:ro
```

#### 方式 2: 环境变量

在 `docker-compose.yml` 中添加：
```yaml
environment:
  - OPENAI_API_KEY=${OPENAI_API_KEY}
  - FMP_API_KEY=${FMP_API_KEY}
```

然后在 `.env` 文件中填写：
```bash
OPENAI_API_KEY=sk-xxx
FMP_API_KEY=xxx
```

## 🐛 故障排除

### 容器无法启动

```bash
# 查看容器日志
docker logs finrobot_app

# 检查配置文件
docker-compose config

# 重新构建镜像
docker-compose build --no-cache
docker-compose up -d
```

### 端口已被占用

```bash
# 查看端口占用
lsof -i :8001

# 修改端口
WEB_PORT=8080 docker-compose up -d
```

### 权限问题

```bash
# 确保配置文件可读
chmod 644 finrobot_equity/core/config/config.ini

# 确保目录可写
chmod 755 finrobot_equity/web_app/data
```

### 数据库连接失败

```bash
# 重建数据卷
docker-compose down -v
docker-compose up -d
```

### 健康检查失败

```bash
# 手动测试健康检查
docker exec finrobot_app python -c "import requests; print(requests.get('http://localhost:8001/health').text)"

# 查看应用日志
docker logs finrobot_app --tail 100
```

## 📊 性能优化

### 资源限制

在 `docker-compose.yml` 中添加资源限制：
```yaml
services:
  finrobot:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

### 缓存优化

利用 Docker 层缓存：
```dockerfile
# 先复制依赖文件
COPY requirements.txt requirements-equity.txt web_requirements.txt ./

# 安装依赖（如果依赖没变，会使用缓存）
RUN pip install -r requirements.txt && ...

# 最后复制代码
COPY . .
```

## 🔒 安全建议

1. **不要在镜像中包含 API Keys**
   - 使用环境变量或配置文件挂载
   - 将配置文件加入 `.gitignore`

2. **使用只读挂载配置文件**
   ```yaml
   volumes:
     - ./config:/app/config:ro  # ro 表示只读
   ```

3. **限制容器权限**
   ```yaml
   security_opt:
     - no-new-privileges:true
   read_only: true
   tmpfs:
     - /tmp
   ```

4. **定期更新基础镜像**
   ```bash
   docker pull python:3.10-slim
   docker-compose build --no-cache
   ```

## 📦 导出和导入

### 导出镜像

```bash
# 导出为 tar 文件
docker save finrobot:latest -o finrobot-image.tar

# 导出整个环境（镜像 + Volume）
docker save finrobot:latest -o finrobot-image.tar
docker run --rm -v finrobot_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/finrobot-data.tar.gz /data
```

### 导入镜像

```bash
# 导入镜像
docker load -i finrobot-image.tar

# 导入数据
docker run --rm -v finrobot_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/finrobot-data.tar.gz -C /
```

## 🔗 集成 OpenClaw

可以在 OpenClaw 中创建一个 skill 来管理 FinRobot 容器：

```python
# 示例：启动/停止/检查 FinRobot
import subprocess

def finrobot_start():
    return subprocess.run(["docker-compose", "up", "-d"], cwd="/home/guyii/clawd/code/FinRobot")

def finrobot_stop():
    return subprocess.run(["docker-compose", "down"], cwd="/home/guyii/clawd/code/FinRobot")

def finrobot_status():
    return subprocess.run(["docker-compose", "ps"], cwd="/home/guyii/clawd/code/FinRobot")
```

---

*文档版本: 1.0*
*更新日期: 2026-04-05*
