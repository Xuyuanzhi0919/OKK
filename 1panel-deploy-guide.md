# OKK量化交易系统 - 1Panel部署完整指南

## 📋 部署概览

本指南将帮助您在1Panel面板上部署OKK量化交易系统，包括：
- PostgreSQL + TimescaleDB 数据库
- Redis 缓存服务
- FastAPI 后端服务
- React 前端应用
- Nginx 反向代理

## 🔧 部署前准备

### 1. 服务器要求
- **最低配置**: 2核4G内存，40G硬盘
- **推荐配置**: 4核8G内存，100G硬盘
- **操作系统**: Ubuntu 20.04+ / CentOS 8+
- **已安装**: 1Panel面板、Docker、Docker Compose

### 2. 域名准备
- 准备一个域名（如：trading.yourdomain.com）
- 将域名解析到服务器IP
- 准备SSL证书（可使用1Panel自动申请）

## 🚀 部署步骤

### 步骤1: 上传项目文件

1. **通过1Panel文件管理器上传项目**
   ```bash
   # 建议上传到
   /opt/1panel/apps/okk-trading/
   ```

2. **或通过SSH上传**
   ```bash
   # 克隆项目
   cd /opt/1panel/apps/
   git clone <your-repo-url> okk-trading
   cd okk-trading
   ```

### 步骤2: 配置环境变量

1. **复制并编辑生产环境配置**
   ```bash
   cp .env.prod .env
   nano .env
   ```

2. **修改关键配置**
   ```bash
   # 域名配置
   DOMAIN=trading.yourdomain.com

   # 数据库密码 (请修改为强密码)
   POSTGRES_PASSWORD=your_strong_postgres_password_123

   # Redis密码 (请修改为强密码)
   REDIS_PASSWORD=your_strong_redis_password_456

   # JWT密钥 (请修改为随机字符串)
   SECRET_KEY=your_super_secret_jwt_key_change_this_in_production_789

   # OKX API配置 (请填写您的API密钥)
   OKX_API_KEY=your_okx_api_key
   OKX_SECRET_KEY=your_okx_secret_key
   OKX_PASSPHRASE=your_okx_passphrase
   OKX_SIMULATED=true  # 建议先使用模拟盘测试
   ```

### 步骤3: 配置SSL证书

1. **在1Panel中申请SSL证书**
   - 进入1Panel → 网站 → 证书
   - 添加证书，选择Let's Encrypt
   - 输入域名申请证书
   - *注意：本项目Docker内部不再配置SSL，统一由1Panel处理HTTPS*

### 步骤4: 执行部署

1. **给部署脚本执行权限**
   ```bash
   chmod +x deploy.sh
   ```

2. **执行部署**
   ```bash
   ./deploy.sh
   ```

3. **查看部署状态**
   ```bash
   docker-compose -f docker-compose.prod.yml ps
   ```

### 步骤5: 在1Panel中配置反向代理

1. **进入1Panel → 网站 → 创建网站**
   - 域名：trading.yourdomain.com
   - 类型：反向代理
   - **代理地址：http://127.0.0.1:8088**
   - *注意：这里的 8088 是我们在 docker-compose.prod.yml 中配置的 Nginx 入口端口*

2. **配置SSL**
   - 启用HTTPS
   - 选择之前申请的SSL证书
   - 开启强制HTTPS

3. **高级配置**（可选）
   ```nginx
   # 在1Panel网站配置中添加自定义配置
   client_max_body_size 100M;
   proxy_connect_timeout 30s;
   proxy_send_timeout 30s;
   proxy_read_timeout 30s;
   ```

## 🔍 部署验证

### 1. 检查服务状态
```bash
# 查看所有容器状态
docker-compose -f docker-compose.prod.yml ps

# 查看服务日志
docker-compose -f docker-compose.prod.yml logs -f backend
docker-compose -f docker-compose.prod.yml logs -f frontend
```

### 2. 访问测试
- **前端**: https://trading.yourdomain.com
- **后端API**: https://trading.yourdomain.com/api/
- **API文档**: https://trading.yourdomain.com/api/docs

### 3. 健康检查
```bash
# 检查后端健康状态
curl -f https://trading.yourdomain.com/api/

# 检查数据库连接
docker exec okk_postgres pg_isready -U okk_user -d okk_quant

# 检查Redis连接
docker exec okk_redis redis-cli ping
```

## 🛠️ 常用管理命令

### 容器管理
```bash
# 启动所有服务
docker-compose -f docker-compose.prod.yml up -d

# 停止所有服务
docker-compose -f docker-compose.prod.yml down

# 重启特定服务
docker-compose -f docker-compose.prod.yml restart backend

# 查看实时日志
docker-compose -f docker-compose.prod.yml logs -f

# 进入容器
docker exec -it okk_backend bash
docker exec -it okk_postgres psql -U okk_user -d okk_quant
```

### 数据库管理
```bash
# 备份数据库
docker exec okk_postgres pg_dump -U okk_user okk_quant > backup_$(date +%Y%m%d_%H%M%S).sql

# 恢复数据库
docker exec -i okk_postgres psql -U okk_user okk_quant < backup.sql

# 查看数据库大小
docker exec okk_postgres psql -U okk_user -d okk_quant -c "SELECT pg_size_pretty(pg_database_size('okk_quant'));"
```

### 应用更新
```bash
# 拉取最新代码
git pull origin main

# 重新构建并部署
docker-compose -f docker-compose.prod.yml up -d --build

# 仅重新构建后端
docker-compose -f docker-compose.prod.yml up -d --build backend
```

## 🔒 安全配置

### 1. 防火墙设置
```bash
# 只开放必要端口
ufw allow 22    # SSH
ufw allow 80    # HTTP
ufw allow 443   # HTTPS
ufw enable
```

### 2. 定期备份
```bash
# 创建备份脚本
cat > backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/backups/okk-trading"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# 备份数据库
docker exec okk_postgres pg_dump -U okk_user okk_quant > $BACKUP_DIR/db_$DATE.sql

# 备份配置文件
tar -czf $BACKUP_DIR/config_$DATE.tar.gz .env nginx/

# 清理7天前的备份
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
EOF

chmod +x backup.sh

# 添加到定时任务
crontab -e
# 添加: 0 2 * * * /opt/1panel/apps/okk-trading/backup.sh
```

### 3. 监控配置
```bash
# 创建监控脚本
cat > monitor.sh << 'EOF'
#!/bin/bash
# 检查服务状态
if ! curl -f http://localhost:8000/ > /dev/null 2>&1; then
    echo "Backend service is down, restarting..."
    docker-compose -f docker-compose.prod.yml restart backend
fi
EOF

chmod +x monitor.sh

# 添加到定时任务 (每5分钟检查一次)
# */5 * * * * /opt/1panel/apps/okk-trading/monitor.sh
```

## 🐛 故障排查

### 常见问题

1. **容器启动失败**
   ```bash
   # 查看详细错误日志
   docker-compose -f docker-compose.prod.yml logs backend
   
   # 检查端口占用
   netstat -tlnp | grep :8000
   ```

2. **数据库连接失败**
   ```bash
   # 检查数据库状态
   docker exec okk_postgres pg_isready -U okk_user -d okk_quant
   
   # 查看数据库日志
   docker-compose -f docker-compose.prod.yml logs postgres
   ```

3. **前端无法访问**
   ```bash
   # 检查nginx配置
   docker exec okk_nginx nginx -t
   
   # 重新加载nginx配置
   docker exec okk_nginx nginx -s reload
   ```

4. **SSL证书问题**
   ```bash
   # 检查证书文件
   ls -la nginx/ssl/
   
   # 测试证书有效性
   openssl x509 -in nginx/ssl/cert.pem -text -noout
   ```

### 性能优化

1. **数据库优化**
   ```sql
   -- 连接到数据库
   docker exec -it okk_postgres psql -U okk_user -d okk_quant
   
   -- 查看连接数
   SELECT count(*) FROM pg_stat_activity;
   
   -- 优化配置
   ALTER SYSTEM SET shared_buffers = '256MB';
   ALTER SYSTEM SET effective_cache_size = '1GB';
   SELECT pg_reload_conf();
   ```

2. **Redis优化**
   ```bash
   # 查看Redis内存使用
   docker exec okk_redis redis-cli info memory
   
   # 设置内存限制
   docker exec okk_redis redis-cli config set maxmemory 512mb
   docker exec okk_redis redis-cli config set maxmemory-policy allkeys-lru
   ```

## 📞 技术支持

如果在部署过程中遇到问题，请：

1. 查看相关日志文件
2. 检查配置文件是否正确
3. 确认服务器资源是否充足
4. 验证网络连接是否正常

部署成功后，您就可以开始使用OKK量化交易系统了！记得先在模拟环境中测试所有功能，确认无误后再切换到实盘交易。