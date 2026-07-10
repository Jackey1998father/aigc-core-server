-- ============================================
-- AIGC 用户表（登录权限验证）
-- 数据库：aigc
-- ============================================

CREATE TABLE IF NOT EXISTS aigc_users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     VARCHAR(50)  NOT NULL UNIQUE  COMMENT '登录工号/账号',
    username    VARCHAR(50)  NOT NULL          COMMENT '员工真实姓名',
    password    VARCHAR(255) NOT NULL          COMMENT '密码哈希',
    nickname    VARCHAR(100) DEFAULT ''        COMMENT '昵称',
    status      TINYINT      DEFAULT 1         COMMENT '1=正常 0=禁用',
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户登录表';


-- 插入默认管理员账号（先用 hash_password.py 生成密码哈希替换 <hash>）
-- INSERT INTO aigc_users (user_id, username, password, nickname) VALUES ('admin', '张三', '<hash>', '管理员');
