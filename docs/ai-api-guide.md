# AI 接入新手指南

本指南面向第一次接触 AI 接口的用户，把几个必要概念讲清楚，再说明三种接口格式的区别，最后一步步把它们填进知时。

---

## 一、几个基本概念

### 什么是 API

API（Application Programming Interface，应用程序接口）是一套预先约定好的通信规则，让一个程序可以向另一个程序发送请求并接收结果。在知时里，你发出一段文字，知时按这套规则把请求发给 AI 服务，AI 服务处理后再把回复传回来，显示在对话窗口里。

### 什么是 API Key

API Key 是一串用于身份验证的字符串（通常以 `sk-` 开头），作用类似于账户密码：服务方靠它识别这次请求来自哪个账户，并据此计费。每个账户的 Key 都是独立的，**不要泄露给他人**——拿到你的 Key 的人可以用你的额度。

如何获取：

- **OpenAI 系列（GPT 等）**：在 [platform.openai.com](https://platform.openai.com) 注册后，于「API Keys」页面创建。
- **Claude**：在 [console.anthropic.com](https://console.anthropic.com) 创建。
- **国内模型**（通义千问、智谱、DeepSeek、Kimi 等）：到各自的开放平台注册创建，大多按实际用量计费，国内网络可直接访问。
- **聚合服务**（如 [OpenRouter](https://openrouter.ai)）：用一个 Key 调用多种模型，免于在多个平台分别注册。

### 什么是 URL

URL（统一资源定位符）就是请求要发往的网络地址，对应服务方提供 API 的具体位置。知时支持两种填法：

| 填法 | 示例 | 知时的行为 |
| --- | --- | --- |
| **Base URL（基地址）** | `https://api.openai.com/v1` | 按所选接口格式自动补全后缀路径 |
| **Full URL（完整地址）** | `https://api.openai.com/v1/chat/completions` | 直接使用，不再拼接 |

通常只需填 Base URL；如果你拿到的是带完整路径的地址，也可以直接填到 Full URL 一栏。

---

## 二、三种接口格式，怎么选

不同公司、不同模型所采用的接口规范并不相同。知时支持三种，**选对格式**是成功的前提。

| 格式 | 适用范围 | 默认路径 | 如何判断 |
| --- | --- | --- | --- |
| **OpenAI Chat** | GPT 系列、DeepSeek、通义千问、智谱、Kimi，以及绝大多数国内服务和聚合服务 | `/v1/chat/completions` | 最通用的格式，**不确定时优先选它** |
| **OpenAI Responses** | OpenAI 较新的接口，内置联网搜索、代码执行等工具 | `/v1/responses` | 当服务方文档明确写明使用 Responses 时才选 |
| **Anthropic（Claude Messages）** | Claude 官方及原生兼容服务 | `/v1/messages` | 模型名是 `claude-*`、且服务方声明采用原生 Anthropic 格式时选 |

三者的主要差异在于请求体结构和请求头：

- **OpenAI Chat**：对话内容放在 `messages` 数组里，每条消息标注角色（`system` / `user` / `assistant`）。
- **OpenAI Responses**：采用事件流式（streaming events）结构，对工具调用的支持更原生。
- **Anthropic Messages**：`system` 提示放在顶层而不是消息数组内，消息体采用 `content` 块结构，且请求头需要附带 `anthropic-version` 字段。

**你不必手动构造这些请求**——知时会根据你选择的格式自动打包。你只需要：选对格式 + 填对 Key 和地址。

---

## 三、在知时里一步步配置

1. 打开主界面右下角「知时助手」→ 顶部「设置」→ 新增模型配置。
2. **选 Provider**：按上表判断，不确定就选 **OpenAI Chat**。
3. **填 API Key**：粘贴你申请到的 Key。
4. **填 URL**：
   - 使用官方或标准兼容服务，填 **Base URL**，例如：
     - OpenAI：`https://api.openai.com/v1`
     - Anthropic：`https://api.anthropic.com`
     - DeepSeek：`https://api.deepseek.com/v1`
   - 使用自建或第三方代理：按对方文档给出的地址填写。
5. **填模型名**：例如 `gpt-4o-mini`、`claude-3-5-sonnet-20241022`、`deepseek-chat`。可点击「获取模型列表」由知时自动拉取该服务支持的全部模型名。
6. 保存后发送一句话测试，能正常收到回复即配置成功。

---

## 四、常见问题

| 现象 | 原因与处理 |
| --- | --- |
| 连不上 / 超时 | 多为网络问题。OpenAI、Anthropic 官方接口在国内通常需要代理，在配置中填写 **HTTP Proxy**（如 `http://127.0.0.1:7890`）。国内服务一般可直接访问 |
| 401 鉴权失败 | API Key 填写错误或已失效，重新复制粘贴 |
| 404 路径不对 | Base URL 与 Provider 不匹配（例如把 Anthropic 的地址配成了 OpenAI Chat 格式）。核对格式与地址是否对应 |
| 模型名报错 | 各服务支持的模型名不同，用「获取模型列表」确认准确名称 |
| 需要额外鉴权头 | 部分服务要求自定义请求头，在「额外请求头」一栏以 JSON 格式填写（知时会自动过滤敏感头，并在备份时清除） |

---

## 五、延伸阅读

- [Hoper-J/AI-Guide-and-Demos-zh_CN](https://github.com/Hoper-J/AI-Guide-and-Demos-zh_CN)（3.6k★）—— 系统的中文 AI / LLM 入门教程，从 API 调用讲起，包含 OpenAI SDK 用法，并演示 DeepSeek、通义等国内服务的 Key 获取流程。
- [Anthropic 官方文档（中文）](https://platform.claude.com/docs/zh-CN/build-with-claude/working-with-messages) —— Claude Messages API 的权威说明。
- [OpenAI API 参考](https://developers.openai.com/api/reference/chat-completions/overview/) —— Chat Completions 与 Responses 的官方规范。
