# agent-imagen-skill

一个 Claude Code / Codex skill（`gen-image`）：在对话里直接生图、改图，**不用 API Key**，用的是你自己已登录的 ChatGPT / Google 账号额度。

每次生图前会弹出参数面板，让你选择途径、比例、分辨率和思考强度。

| 途径 | 模型 | 分辨率 | 方式 |
|---|---|---|---|
| GPT Image · Codex | GPT Image（由 OpenAI 自动选择版本） | 约 1.6K | 调用本机 Codex CLI，全自动 |
| GPT Image · ChatGPT 网页 | GPT Image + 可选思考强度 | 约 1.6K | Claude in Chrome 操作 chatgpt.com |
| Nano Banana 2.1 · AI Studio | Nano Banana 2.1，可选思考强度 | 1K / 2K / 4K（最高 5504×3072） | Claude in Chrome 操作 aistudio.google.com |
| Nano Banana 2 · agy | Nano Banana 2 | 1K | 调用本机 Antigravity CLI，全自动 |

## 依赖
- **Codex CLI**，已用 ChatGPT 账号登录（`codex login`）。ChatGPT 桌面版自带一份，也可以 `npm i -g @openai/codex`。
- **Antigravity CLI（agy）**，已用 Google 账号登录：`curl -fsSL https://antigravity.google/cli/install.sh | bash`，然后运行一次 `agy` 登录。
- 网页途径需要 **Claude in Chrome** 扩展，并在 Chrome 里登录好 ChatGPT / AI Studio（只能在 Claude 端使用）。
- macOS（脚本用到了 `sips`）。

## 安装
```bash
git clone https://github.com/FIONN191/agent-imagen-skill.git ~/.claude/skills/gen-image
```
Codex 用户可以克隆到 `~/.codex/skills/gen-image`。

## 使用
在 Claude Code 里直接说「画一张……」「把这张图改成……」，按面板选择参数即可。图片默认保存在 `~/Pictures/AI生图/`。

命令行途径也可以单独运行：
```bash
bash scripts/gen.sh -e gpt|nb|both -a 16:9 -p "提示词" [-i 参考图.png] [-o 输出目录] [-n 张数]
```

## 说明
- 所有途径都使用官方客户端或官方网页，不调用非官方私有接口。Codex 以只读沙箱运行，agy 以 `--sandbox` 运行。
- 经实测，GPT Image 在订阅额度下（Codex 和 ChatGPT 网页都一样）输出固定约 1672×941（16:9），在提示词里要求 4K 也不会变。要 2K/4K 请用 AI Studio 途径。
- 网页途径保存图片走 Chrome 的正常下载；如果 Chrome 开着「下载前询问保存位置」，需要手动点一下「存储」，`scripts/collect.sh` 会把文件移到输出目录。
- 生图会消耗你自己账号的额度，请遵守 OpenAI 和 Google 的服务条款。
