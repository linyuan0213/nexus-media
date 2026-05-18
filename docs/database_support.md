# 多数据库支持文档

本文档说明 Nexus Media 的多数据库支持功能，包括 SQLite、MySQL 和 PostgreSQL。

## 概述

Nexus Media 现在支持以下三种数据库：

1. **SQLite** (默认) - 本地文件数据库，无需额外配置
2. **MySQL** - 高性能关系型数据库，适合高并发场景
3. **PostgreSQL** - 功能强大的开源关系型数据库

## 配置方法

支持两种方式配置数据库：**环境变量**（优先级更高）或 **配置文件**。

### 环境变量配置（推荐 Docker/K8s 使用）

支持以下环境变量，启动时会自动写入配置文件：

| 环境变量 | 说明 | 示例 |
|---------|------|------|
| `DB_TYPE` | 数据库类型 | `sqlite` / `mysql` / `postgresql` |
| `DB_HOST` | 数据库主机 | `localhost` |
| `DB_PORT` | 数据库端口 | `3306` / `5432` |
| `DB_USERNAME` | 用户名 | `nastools` |
| `DB_PASSWORD` | 密码 | `your_password` |
| `DB_NAME` | 数据库名 | `nas_tools` |

**Docker 示例：**
```bash
docker run -e DB_TYPE=mysql \
           -e DB_HOST=mysql-server \
           -e DB_PORT=3306 \
           -e DB_USERNAME=nastools \
           -e DB_PASSWORD=secret \
           -e DB_NAME=nas_tools \
           linyuan0213/nexus-media:latest
```

### 配置文件配置

在 `config/config.yaml` 中添加 `database` 配置项：

### SQLite (默认配置)

```yaml
database:
  type: sqlite
```

SQLite 不需要其他配置，数据库文件会自动创建在配置目录下的 `user.db`。

### MySQL 配置

```yaml
database:
  type: mysql
  host: localhost
  port: 3306
  username: nastools
  password: your_password
  database: nas_tools
```

**注意：** 程序会自动创建数据库，无需手动执行 SQL。

### PostgreSQL 配置

```yaml
database:
  type: postgresql
  host: localhost
  port: 5432
  username: postgres
  password: your_password
  database: nas_tools
```

**注意：** 程序会自动创建数据库，无需手动执行 SQL。

## 数据库迁移

### 从 SQLite 迁移到 MySQL/PostgreSQL

1. **备份现有数据**
   ```bash
   cp config/user.db config/user.db.backup
   cp config/media.db config/media.db.backup
   ```

2. **导出 SQLite 数据**
   ```bash
   sqlite3 config/user.db .dump > user_dump.sql
   sqlite3 config/media.db .dump > media_dump.sql
   ```

3. **修改配置文件**
   按照上面的配置方法修改为 MySQL 或 PostgreSQL

4. **重新启动程序**
   程序会自动创建表结构

5. **导入数据**（可选）
   根据需要导入历史数据

## 技术细节

### 数据库连接池

- **SQLite**: 使用 QueuePool (主库) 或 NullPool (媒体库)
- **MySQL/PostgreSQL**: 使用 QueuePool，默认配置：
  - `pool_size`: 20
  - `max_overflow`: 40
  - `pool_timeout`: 60秒
  - `pool_recycle`: 3600秒

### SQL 语法适配

系统自动处理以下 SQL 语法差异：

| 功能 | SQLite | MySQL | PostgreSQL |
|------|--------|-------|------------|
| 忽略重复插入 | `INSERT OR IGNORE` | `INSERT IGNORE` | `INSERT ... ON CONFLICT DO NOTHING` |
| 删除所有 | `DELETE WHERE 1` | `DELETE WHERE 1` | `DELETE WHERE TRUE` |
| 当前时间 | `datetime('now')` | `NOW()` | `CURRENT_TIMESTAMP` |
| 随机数 | `RANDOM()` | `RAND()` | `RANDOM()` |
| 字符串连接 | `||` | `CONCAT()` | `||` |
| 日期格式化 | `strftime()` | `DATE_FORMAT()` | `TO_CHAR()` |

### 注意事项

1. **MySQL/PostgreSQL 需要先创建数据库**
   - 主数据库: `{database_name}`
   - 媒体数据库: `{database_name}_media`

2. **字符集**
   - MySQL 建议使用 `utf8mb4` 以支持完整的 Unicode 字符
   - PostgreSQL 默认使用 UTF-8

3. **权限**
   - 数据库用户需要 CREATE、INSERT、UPDATE、DELETE、SELECT 权限
   - 对于迁移，还需要 ALTER 权限

## 故障排除

### 连接失败

**MySQL:**
- 检查 MySQL 服务是否运行
- 检查用户名和密码
- 检查防火墙设置
- 确认数据库已创建

**PostgreSQL:**
- 检查 PostgreSQL 服务是否运行
- 检查 pg_hba.conf 认证配置
- 确认数据库已创建

### 性能问题

1. **MySQL/PostgreSQL 连接慢**
   - 检查网络延迟
   - 启用连接池 `pool_pre_ping=True`

2. **高并发场景**
   - 增加 `pool_size` 和 `max_overflow`
   - 考虑使用读写分离

## API 参考

### DatabaseFactory

```python
from app.db.database_factory import DatabaseFactory

# 创建引擎
engine = DatabaseFactory.create_engine(db_type='mysql')

# 获取连接URL
url = DatabaseFactory.get_database_url(
    db_type='postgresql',
    host='localhost',
    port=5432,
    username='user',
    password='pass',
    database='nas_tools'
)

# 检测数据库类型
is_sqlite = DatabaseFactory.is_sqlite(engine)
is_mysql = DatabaseFactory.is_mysql(engine)
is_postgresql = DatabaseFactory.is_postgresql(engine)
```

### SQLAdapter

```python
from app.db.sql_adapter import SQLAdapter, adapt_sql_for_engine

# 创建适配器
adapter = SQLAdapter(engine)

# 适配 SQL 语句
sql = 'INSERT OR IGNORE INTO table (id) VALUES (1)'
adapted_sql = adapter.adapt_sql(sql)

# 获取特定数据库的函数
timestamp_func = adapter.get_current_timestamp()  # NOW(), CURRENT_TIMESTAMP, etc.
random_func = adapter.get_random_function()  # RAND(), RANDOM(), etc.
```


