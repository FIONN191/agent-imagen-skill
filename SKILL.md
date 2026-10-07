---
name: gen-image
description: "无需 API Key 的生图/改图：生成前先弹出参数面板让用户选途径、比例、分辨率、思考强度，再调用本机已登录账号的 Codex CLI（GPT Image）、ChatGPT 网页（GPT Image，可选思考强度）、AI Studio 网页（Nano Banana 2.1，1K/2K/4K）或 Antigravity CLI agy（Nano Banana 2）。用户要求生成图片、画一张图、出图、做海报/插画/概念图、按参考图改图/换风格/换背景，或点名 GPT Image、ChatGPT、Nano Banana、香蕉、Gemini、AI Studio、4K 生图时使用。不用于 Photoshop 内修图、视频生成，也不要改用 Higgsfield 等按次付费的生图工具，除非用户明确要求。"
---

# gen-image：用个人账号生图（GPT Image / Nano Banana）

## 第一步：弹参数面板（每次生图都要）
用户提出生图需求后，**先用 AskUserQuestion 弹一个面板**，一次问完下面 4 个问题，不要让用户打字。用户的提示词照常从对话里取。

| header | question | multiSelect | options（label — description） |
|---|---|---|---|
| 途径 | 用哪个模型和途径生成？（可多选对比） | true | **GPT Image · Codex** — 官方 Codex CLI，约 1.6K，中文排版强，1–2 分钟，全自动<br>**GPT Image · ChatGPT 网页** — Chrome 里的 ChatGPT（Business），约 1.6K，思考强度可选，高强度提示词改写更细；需点「存储」<br>**Nano Banana 2.1 · AI Studio** — Chrome 里的 AI Studio，1K/2K/4K 和思考强度可选，最高 5504×3072；需点「存储」<br>**Nano Banana 2 · agy** — Antigravity CLI，1K，最快，全自动 |
| 比例 | 画面比例？ | false | **16:9** / **9:16** / **1:1** / **4:3**（其他比例如 3:4、21:9、3:2 让用户选 Other 填写） |
| 分辨率 | 分辨率？（仅 AI Studio 生效；GPT 固定约 1.6K，agy 固定 1K） | false | **2K** / **4K** — 16:9 时 5504×3072，较慢 / **1K** |
| 思考强度 | 思考强度？（ChatGPT 网页 / AI Studio 生效；Codex、agy 不适用） | false | **最高** — ChatGPT: Extra High；AI Studio: High<br>**中等** — ChatGPT: Medium；AI Studio: Medium<br>**最快** — ChatGPT: Instant；AI Studio: Minimal |

- 选项排序：本对话里用户上次的选择放第一位，label 后加「（上次）」；没有上次就按上表顺序，第一项加「(Recommended)」。
- 用户已在请求里写明的项（比如「用 AI Studio 出 4K 横图」）直接采用，面板只问剩下的。四项都写明了，或用户说「直接生成」「同上」「按上次设置」，就跳过面板。
- 比例超出引擎支持范围时（例如 agy 选了 21:9），用最接近的比例并告诉用户。
- 在 Codex 端没有这个面板工具：用一句话列出默认选择（Codex 内置生图、比例按需求），用户不改就直接生成。

## 第二步：按选择执行
| 途径 | 怎么跑 |
|---|---|
| GPT Image · Codex | `scripts/gen.sh -e gpt`（见下方「调用」） |
| Nano Banana 2 · agy | `scripts/gen.sh -e nb` |
| 两个命令行途径都选了 | `scripts/gen.sh -e both` |
| GPT Image · ChatGPT 网页 | 浏览器步骤见 [references/chatgpt-web.md](references/chatgpt-web.md)，只在 Claude 端可用 |
| Nano Banana 2.1 · AI Studio | 浏览器步骤见 [references/aistudio.md](references/aistudio.md)，只在 Claude 端可用 |

多选时：命令行途径用 `run_in_background` 先跑起来，同时做浏览器途径；两个浏览器途径之间依次做（共用一个 Chrome）。全部完成后一起交付，并注明每张图来自哪个途径、用了什么参数。

GPT 两个途径都不能指定 Sunburst / Flare 或尺寸，由 OpenAI 自动决定。

## 调用
```bash
bash <skill-root>/scripts/gen.sh -e gpt -a 9:16 -p "<提示词>" [-i 参考图.png ...] [-o 输出目录] [-n 张数] [-t 文件名前缀]
```
- `-a` 比例：`1:1`（默认）`16:9` `9:16` `4:3` `3:4`。
- `-i` 参考/待改图，可重复；必须是磁盘上的文件路径。用户在对话里贴的图如果没有路径，请用户给出文件路径。
- `-o` 默认 `~/Pictures/AI生图/`；用户在某个项目里工作且说"放到项目里"时用项目内目录。
- `-n` 每个引擎的张数，并行生成。
- 提示词直接用用户的语言写清楚：主体、场景、风格、构图、要出现的文字（用引号标出原文）。用户给的描述太简略时可以帮着补全，但不要改掉用户点名的要素。

**Bash 调用必须设 `timeout: 600000`**：单张 GPT 约 1–2 分钟，Nano Banana 约 1–3 分钟。`both` 或 `-n` ≥ 3 时用 `run_in_background`，结束后会收到通知。

## 输出与交付
- 脚本每张图打印一行 `SAVED: <路径> (<宽>x<高>)`；全部失败时退出码为 1，并在 stderr 打印日志位置和末尾几行。
- 拿到路径后先查看图片、确认符合要求，再交给用户：
  - **Claude**：用 Read 查看，再用 SendUserFile（`display: render`）发图，并附上保存路径。
  - **Codex**：用本地图片查看能力检查后，在回复里给出保存路径。
- 改图迭代：把上一张输出作为 `-i` 再跑一次。

## 在 Codex 里使用
Codex 自带 GPT Image 生图：用户要 GPT 出图时，直接用内置生图工具，生成后把文件复制到输出目录，不要通过本脚本再套一层 `codex exec`。本脚本在 Codex 里只用 `-e nb`。ChatGPT 网页和 AI Studio 两个途径依赖 Claude in Chrome，Codex 端不可用；用户在 Codex 里要用它们时，请他到 Claude 里生成。如果 agy 因沙箱无法联网或无法写 `~/.gemini`，请用户批准该命令越过沙箱运行。

## 须知
- 分辨率：GPT（Codex 和 ChatGPT 网页一样）约 1672×941（16:9）/ 941×1672（9:16），提示词里要求 4K 也不变；agy 的 Nano Banana 2 约 1376×768；只有 AI Studio 的 Nano Banana 2.1 能出 2K/4K。
- 额度：分别消耗用户的 ChatGPT（Codex）额度和 Google（Antigravity 生图）额度，不额外花钱。提示额度用尽时如实转告用户，不要自动换成付费工具。
- 脚本以只读沙箱运行 Codex（`-s read-only`）、以 `--sandbox` 运行 agy，**不要**加 `--dangerously-skip-permissions` / `--dangerously-bypass-approvals-and-sandbox`。

## 故障排查
| 现象 | 处理 |
|---|---|
| `Codex CLI not found` | 装 ChatGPT/Codex 桌面版，或 `npm i -g @openai/codex` 后运行 `codex login` |
| Codex 报未登录 | 让用户在终端运行 `codex login`（浏览器登录 ChatGPT） |
| `Antigravity CLI not found` | `curl -fsSL https://antigravity.google/cli/install.sh \| bash` |
| agy 要求登录 / 无模型 | 让用户在终端运行一次 `agy`，选 Google OAuth 登录 |
| agy 提示 quota / limit | Nano Banana 额度用完，改用 `-e gpt` 或等额度刷新 |
| 没有 SAVED 输出 | 查看 stderr 给出的日志目录里的 `log.jsonl` / `log.txt` |
