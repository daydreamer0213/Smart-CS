# Phase 1.2: JWT 认证 — 设计 Spec

**日期:** 2026-06-24
**状态:** approved
**前置:** Phase 1.1 文档导入（已完成）

## 目标

替换当前纯 API Key 认证为 JWT，新增用户注册/登录体系。API Key 保留给 M2M/脚本调用，JWT 给人类管理员使用。

## 设计决策

| 决策 | 选择 |
|------|------|
| 用户-租户关系 | 一对一（User 有 tenant_id FK） |
| 角色 | owner / admin / agent 三级 |
| 注册 | 公开注册（有邮箱即可） |
| Token | access（15min）+ refresh（7d），refresh 轮换 |
| API Key | 保留，M2M 专用，不走 JWT |
| 实现方案 | 轻量自建：python-jose + passlib |
| 升级空间 | 预留 jti、type payload 字段；get_current_user 依赖接口可替换 |

## 模块划分

```
新增:
  app/models/user.py             — User 模型
  app/schemas/auth.py            — 注册/登录/刷新 request/response
  app/api/auth.py                — POST /api/v1/auth/{register,login,refresh}
  app/core/auth/__init__.py
  app/core/auth/token.py         — JWT 签发 + 验证
  app/core/auth/security.py      — 密码哈希 + 验证
  tests/test_auth.py             — 认证测试

改动:
  app/config.py                  — 加 jwt_secret, jwt_algorithm, token 过期配置
  app/models/__init__.py         — 导出 User
  app/api/deps.py                — 加 get_current_user
  app/api/admin/auth.py          — verify_admin 保留，加 require_admin / require_owner
  app/main.py                    — 注册 auth_router
```

边界规则：`core/auth/` 不依赖 FastAPI，`api/` 层只做参数提取和错误转换。

## 数据模型

### User

```python
class User(Base, TimestampMixin):
    __tablename__ = "users"

    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    display_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False, default="agent")  # owner|admin|agent
    is_active = Column(Boolean, default=True, nullable=False)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)

    tenant = relationship("Tenant")
```

AdminApiKey 表不变，独立运作。

### 关系

```
Tenant 1 — N User
Tenant 1 — N AdminApiKey
User   N — 1 Tenant
```

### 约束

- email 全局唯一，注册时检查 → 409
- role in (owner, admin, agent)
- owner 注册 → 自动创建 Tenant（slug + name 必传）
- admin/agent 注册 → tenant_slug 必传，绑定已有租户
- 密码最少 8 字符，至少 1 字母 + 1 数字

## API

### POST /api/v1/auth/register

```json
// Request
{
  "email": "admin@example.com",
  "password": "min8chars",
  "display_name": "张三",
  "role": "owner",
  "tenant_slug": "demo",        // 非 owner 必填
  "tenant_name": "Demo商城"     // owner 必填
}

// Response 201
{
  "user": {
    "id": "uuid",
    "email": "admin@example.com",
    "display_name": "张三",
    "role": "owner",
    "tenant_slug": "demo"
  },
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

### POST /api/v1/auth/login

```json
// Request
{ "email": "admin@example.com", "password": "min8chars" }

// Response 200 — 同 register 结构
```

### POST /api/v1/auth/refresh

```json
// Request
{ "refresh_token": "eyJ..." }

// Response 200
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",    // 轮换新 token
  "token_type": "bearer"
}
```

错误格式沿用现有约定：
```json
{"error": {"code": "INVALID_CREDENTIALS", "message": "..."}, "request_id": "..."}
```

## 认证依赖

```
get_current_user          → Bearer token → decode JWT → 查 User → 返回 User
require_admin(user)       → get_current_user + 检查 role in (owner, admin)
require_owner(user)       → get_current_user + 检查 role == owner
verify_admin(X-Admin-Key) → 保留不变（原函数改名 get_api_key，语义更准）
```

Admin 路由迁移后，从 `Depends(verify_admin)` 变为 `Depends(require_admin)`，直接拿 User 对象，通过 `user.tenant` 获取租户信息。

## JWT Payload

```json
{
  "sub": "<user_id>",
  "tenant_id": "<tenant_id>",
  "role": "owner",
  "jti": "<uuid>",
  "type": "access",
  "exp": 1719234567
}
```

- `jti` 现在不用，预留后续 Token 撤销
- `type` 区分 access/refresh，验证时检查防混用
- `tenant_id` 在 token 里，不依赖 URL slug 推租户

## 配置

```python
# .env 新增
JWT_SECRET=           # 生产必填，开发留空则自动生成随机 secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```

## 安全

| 项 | 做法 |
|----|------|
| 密码存储 | bcrypt，cost factor 12 |
| Token 类型隔离 | payload.type 检查，refresh 不能当 access |
| Refresh 轮换 | 用一次签发新的 |
| 密码强度 | >=8 字符，至少 1 字母 + 1 数字 |
| tenant_id 安全 | 从 token payload 取，不从 URL 猜测 |

## 测试

`tests/test_auth.py`：

- 注册：owner 创建租户、admin 绑定已有租户、重复邮箱 409、弱密码 422
- 登录：正确凭证 200、错误密码 401、不存在邮箱 401、disabled 用户 401
- Refresh：有效 refresh 200、过期 refresh 401、access token 当 refresh 401
- get_current_user：无 token / 无效 / 格式错 / 过期 → 401
- require_admin / require_owner：agent 访问 admin 路由 → 403
- 回归：现有 94 个测试不受影响，API Key 路由仍然可用
