-- AIOW PostgreSQL 初始化脚本
-- 启用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- gen_random_uuid() 由 pgcrypto 提供
