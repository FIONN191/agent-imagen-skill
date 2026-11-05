# agent-imagen-skill

一个 Claude Code / Codex skill（`gen-image`）：在对话里直接生图、改图。可以用你自己的 **OpenAI API Key**（GPT Image 2.6，按量计费，模型、尺寸、质量都能指定），也可以**不用 API Key**，直接用你已登录的 ChatGPT / Google 账号额度。

每次生图前会弹出参数面板，让你选择途径、比例、分辨率和思考强度。

| 途径 | 模型 | 分辨率 | 方式 | 费用 |
|---|---|---|---|---|
| GPT Image 2.6 · OpenAI API | gpt-image-2.6-sunburst / flare（可换 2.5、2） | 1K / 2K / 4K（最高 3840×2160），支持透明背景、蒙版 | 调用官方 Images API，全自动 | 你的 API Key 按量计费 |
| GPT Image · Codex | GPT Image（由 OpenAI 自动选择版本） | 约 1.6K | 调用本机 Codex CLI，全自动 | ChatGPT 订阅额度 |
| GPT Image · ChatGPT 网页 | GPT Image + 可选思考强度 | 约 1.6K | Claude in Chrome 操作 chatgpt.com | ChatGPT 订阅额度 |
| Nano Banana 2.1 · AI Studio | Nano Banana 2.1，可选思考强度 | 1K / 2K / 4K（最高 5504×3072） | Claude in Chrome 操作 aistudio.google.com | Google 账号额度 |
| Nano Banana 2 · agy | Nano Banana 2 | 1K | 调用本机 Antigravity CLI，全自动 | Google 账号额度 |

## 依赖
- **OpenAI API 途径**：`python3`（macOS 装过 Xcode 命令行工具就有，否则运行 `xcode-select --install`），以及一个 OpenAI API Key，见下方「配置 OpenAI API Key」。
- **Codex CLI**，已用 ChatGPT 账号登录（`codex login`）。ChatGPT 桌面版自带一份，也可以 `npm i -g @openai/codex`。
- **Antigravity CLI（agy）**，已用 Google 账号登录：`curl -fsSL https://antigravity.google/cli/install.sh | bash`，然后运行一次 `agy` 登录。
- 网页途径需要 **Claude in Chrome** 扩展，并在 Chrome 里登录好 ChatGPT / AI Studio（只能在 Claude 端使用）。
- macOS（Codex、agy 和网页途径用到了 `sips` 和 Chrome 下载目录；OpenAI API 途径在 Linux 上也能用）。

## 安装
```bash
git clone https://github.com/FIONN191/agent-imagen-skill.git ~/.claude/skills/gen-image
```
Codex 用户可以克隆到 `~/.codex/skills/gen-image`。

## 配置 OpenAI API Key（只有 API 途径需要）
1. 在 [platform.openai.com/api-keys](https://platform.openai.com/api-keys) 创建 Key，并在 Billing 里充值（ChatGPT 会员不含 API 额度）。
2. 组织要先完成验证才能用 GPT Image：Settings → Organization → General → **Verify Organization**，通过后约 15 分钟生效。
3. 复制配置模板，把 Key 填在 `OPENAI_API_KEY=` 后面：
   ```bash
   cd ~/.claude/skills/gen-image
   cp .env.example .env && chmod 600 .env
   open -e .env
   ```
   `.env` 已在 `.gitignore` 里，不会被提交。访问 OpenAI 需要代理时，在里面填 `HTTPS_PROXY=http://127.0.0.1:7890`；默认模型、质量、分辨率也可以在这里改。
4. 自检（不生图、不花钱）：
   ```bash
   python3 scripts/openai_image.py --check
   ```

不想用文件也可以在 shell 里 `export OPENAI_API_KEY=...`。只有 `.env` 里没填 Key 时才会读这个环境变量。

## 使用
在 Claude Code 里直接说「画一张……」「把这张图改成……」，按面板选择参数即可。图片默认保存在 `~/Pictures/AI生图/`。

命令行途径也可以单独运行：
```bash
bash scripts/gen.sh -e api -a 16:9 -r 2K -p "提示词"                         # OpenAI API，2560×1440
bash scripts/gen.sh -e api -m flare -c low -r 1K -p "提示词"                  # 最快
bash scripts/gen.sh -e api -b transparent -a 1:1 -p "一只猫的扁平 Logo"        # 透明背景 PNG
bash scripts/gen.sh -e api -i 原图.png -M 蒙版.png -p "把框里换成一盆花"         # 局部重绘
bash scripts/gen.sh -e gpt|api|nb|both|all -a 16:9 -p "提示词" [-i 参考图.png] [-o 输出目录] [-n 张数]
python3 scripts/openai_image.py --help                                      # API 途径的全部参数
```
API 的模型、尺寸对照、参数、费用和报错处理见 [references/openai-api.md](references/openai-api.md)。

## 说明
- 免 Key 途径都使用官方客户端或官方网页，不调用非官方私有接口。Codex 以只读沙箱运行，agy 以 `--sandbox` 运行。
- API 途径直接调用 OpenAI 官方 Images API。Key 只从 `.env` 或环境变量读取，不会被打印，也不会出现在命令行参数里。
- 经实测，GPT Image 在订阅额度下（Codex 和 ChatGPT 网页都一样）输出固定约 1672×941（16:9），在提示词里要求 4K 也不会变。要 2K/4K 请用 OpenAI API 或 AI Studio 途径。
- 网页途径保存图片走 Chrome 的正常下载；如果 Chrome 开着「下载前询问保存位置」，需要手动点一下「存储」，`scripts/collect.sh` 会把文件移到输出目录。
- OpenAI API 按 token 计费：2.6 的 1024×1024 单张 high 质量约 $0.05，4K 或 xhigh / max 质量会贵很多（第三方估算，以[官方价格](https://openai.com/api/pricing)为准）。
- 生图会消耗你自己账号的额度或 API 余额，请遵守 OpenAI 和 Google 的服务条款。
