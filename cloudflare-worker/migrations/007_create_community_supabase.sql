-- ==========================================================
-- Supabase 社区留言板、待办任务与系统公告表结构迁移脚本
-- 复制并在 Supabase 控制台的 SQL Editor 中一键运行即可
-- ==========================================================

-- 1. 启用 pgvector 向量扩展 (为未来留言、求歌及语义推荐预留)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 官方系统公告表
CREATE TABLE IF NOT EXISTS public.system_notices (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    author_name TEXT DEFAULT '音信官方',
    is_pinned BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. 社区帖子与待办任务表
CREATE TABLE IF NOT EXISTS public.community_posts (
    id BIGSERIAL PRIMARY KEY,
    category TEXT NOT NULL CHECK (category IN ('chat', 'resource', 'bug', 'ui', 'feature')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    author_name TEXT NOT NULL,
    author_avatar TEXT,
    is_task BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed')),
    is_pinned BOOLEAN DEFAULT FALSE,
    comment_count INTEGER DEFAULT 0,
    embedding vector(1536), -- 预留 OpenAI / Gemini 嵌入向量，方便做求歌/Bug相似度聚类
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. 社区跟帖回复评论表
CREATE TABLE IF NOT EXISTS public.community_comments (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT REFERENCES public.community_posts(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    author_name TEXT NOT NULL,
    author_avatar TEXT,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. 创建索引以优化高频查询
CREATE INDEX IF NOT EXISTS idx_supabase_posts_category ON public.community_posts(category);
CREATE INDEX IF NOT EXISTS idx_supabase_posts_status ON public.community_posts(status);
CREATE INDEX IF NOT EXISTS idx_supabase_posts_user ON public.community_posts(user_id);
CREATE INDEX IF NOT EXISTS idx_supabase_comments_post ON public.community_comments(post_id);

-- 6. 预置初始官方公告数据
INSERT INTO public.system_notices (title, content, author_name, is_pinned)
VALUES 
(
    '欢迎来到《音信 · TunePost》人文音乐杂志',
    '感谢每一位朋友的相遇。在音信，我们推崇慢节奏的黑胶质感与纯粹的聆听体验。本应用涵盖了多位华语与经典音乐名家的精选唱片。若在使用中有任何体验建议、想听的音乐或者遇到的问题，欢迎在留言板各板块畅所欲言！',
    '音信团队',
    TRUE
),
(
    '音信社区与待办系统正式上线说明',
    '本次更新带来了全新的抽屉布局与读者回响中心！留言板现已按【吐槽闲聊】、【资源补齐】、【Bug提示】、【页面优化】、【功能缺失】五大板块细分。对于任务类反馈，开发者将以待办事项清单（Todo List）形式跟进，做完一个打钩一个，所有更新对全员公开透明！',
    'Master 开发者',
    TRUE
)
ON CONFLICT DO NOTHING;
