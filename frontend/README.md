# ActReply 前端应用

基于 Vue 3 + Vite + TypeScript + Tailwind CSS 4 的智能助手前端界面。

## 功能特性

### ✅ 已实现功能

- **用户认证**
  - JWT 双 Token 认证（Access + Refresh）
  - 注册/登录界面
  - Token 自动刷新
  - 路由守卫保护

- **会话管理**
  - 创建新对话
  - 会话列表展示（侧边栏）
  - 删除会话
  - 会话切换
  - 自动保存会话状态

- **实时对话**
  - SSE 流式响应
  - 实时打字效果
  - 工具调用可视化
  - 思考过程展示
  - 错误处理和重试提示
  - 迭代进度显示

- **文件支持**
  - 图片上传（PNG, JPEG, GIF, WebP）
  - PDF 文档上传
  - Word 文档上传（DOCX）
  - PPT 演示文稿上传（PPTX）
  - 文件预览
  - 文件处理状态跟踪

- **界面设计**
  - 响应式布局（移动端 + 桌面端）
  - 亚克力毛玻璃风格
  - 深色模式支持
  - 流畅动画效果
  - Markdown 渲染
  - 代码高亮

## 技术栈

- **框架**: Vue 3 (Composition API)
- **构建工具**: Vite
- **语言**: TypeScript
- **状态管理**: Pinia
- **路由**: Vue Router
- **样式**: Tailwind CSS 4
- **图标**: Lucide Vue Next
- **Markdown**: Marked
- **代码高亮**: Shiki

## 开发指南

### 安装依赖

```bash
bun install
```

### 开发模式

```bash
bun dev
```

访问 <http://localhost:5173>

### 构建生产版本

```bash
bun run build
```

## 配置说明

### Vite 配置

`vite.config.ts` 中已配置：

- API 代理：`/api` -> `http://localhost:8713`
- 路径别名：`@` -> `src/`

### 后端 API 地址

开发环境通过 Vite 代理自动转发到 `http://localhost:8713`

## 使用说明

### 1. 启动后端服务

### 2. 启动前端开发服务器

```bash
cd frontend
bun dev
```

### 3. 注册/登录

- 访问 <http://localhost:5173>
- 首次使用需要注册账号
- 输入注册令牌

### 4. 开始对话

- 点击"新建对话"创建新会话
- 输入消息并发送
- 支持上传文件（点击回形针图标）

## 响应式设计

- **移动端** (< 1024px): 侧边栏折叠，单列布局
- **桌面端** (>= 1024px): 侧边栏固定，多列布局

## 组件风格

所有组件遵循统一设计系统：

- **颜色**: 蓝色主题（from-blue-500 to-blue-600）
- **圆角**: rounded-xl, rounded-2xl
- **背景**: 亚克力风格（backdrop-blur-md）
- **动画**: transition-all
