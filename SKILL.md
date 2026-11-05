---
name: gen-image
description: "生图/改图：生成前先弹出参数面板让用户选途径、比例、分辨率、思考强度，再调用 OpenAI API（GPT Image 2.6 Sunburst/Flare，用户自填 API Key、按量计费，最高 3840×2160，可透明背景、蒙版局部重绘）、本机已登录账号的 Codex CLI（GPT Image）、ChatGPT 网页、AI Studio 网页（Nano Banana 2.1，1K/2K/4K）或 Antigravity CLI agy（Nano Banana 2）。用户要求生成图片、画一张图、出图、做海报/插画/概念图/Logo/透明底素材、按参考图改图/换风格/换背景/局部重绘，或点名 GPT Image、Sunburst、Flare、OpenAI API、ChatGPT、Nano Banana、香蕉、Gemini、AI Studio、4K 生图时使用。不用于 Photoshop 内修图、视频生成，也不要改用 Higgsfield 等第三方付费生图工具，除非用户明确要求。"
---

# gen-image：生图 / 改图（GPT Image / Nano Banana）

## 第一步：弹参数面板（每次生图都要）
用户提出生图需求后，**先用 AskUserQuestion 弹一个面板**，一次问完下面 4 个问题，不要让用户打字。用户的提示词照常从对话里取。

| header | question | multiSelect | options（label — description） |
|---|---|---|---|
| 途径 | 用哪个模型和途径生成？（可多选对比） | true | **GPT Image 2.6 · OpenAI API** — 你自己的 API Key，按量计费；Sunburst/Flare、最高 4K（3840×2160）、透明背景，全自动<br>**GPT Image · Codex** — 官方 Codex CLI，订阅额度，约 1.6K，中文排版强，1–2 分钟，全自动<br>**Nano Banana 2.1 · AI Studio** — Chrome 里的 AI Studio，1K/2K/4K 和思考强度可选，最高 5504×3072；需点「存储」<br>**Nano Banana 2 · agy** — Antigravity CLI，1K，最快，全自动 |
| 比例 | 画面比例？ | false | **16:9** / **9:16** / **1:1** / **4:3**（其他比例如 3:4、21:9、3:2 让用户选 Other 填写） |
| 分辨率 | 分辨率？（AI Studio / OpenAI API 生效；Codex、ChatGPT 网页固定约 1.6K，agy 固定 1K） | false | **2K** — API 16:9 为 2560×1440<br>**4K** — AI Studio 16:9 为 5504×3072；API 为 3840×2160（实验性）；都较慢，API 更贵<br>**1K** — 最快最省 |
| 思考强度 | 思考强度？（OpenAI API / ChatGPT 网页 / AI Studio 生效；Codex、agy 不适用） | false | **最高** — API: Sunburst + 规划 high；ChatGPT: Extra High；AI Studio: High<br>**中等** — API: Sunburst + 规划 medium；ChatGPT: Medium；AI Studio: Medium<br>**最快** — API: Flare + 规划 low；ChatGPT: Instant；AI Studio: Minimal |

- 面板每题最多 4 个选项，所以 **GPT Image · ChatGPT 网页**（订阅额度、思考强度可选、需点「存储」）不在选项里：用户选 Other 填「ChatGPT 网页」，或在请求里点名时照常使用。
- 选项排序：本对话里用户上次的选择放第一位，label 后加「（上次）」；没有上次就按上表顺序，第一项加「(Recommended)」。
- 用户已在请求里写明的项（比如「用 AI Studio 出 4K 横图」「API 用 Flare 出 2K」）直接采用，面板只问剩下的。四项都写明了，或用户说「直接生成」「同上」「按上次设置」，就跳过面板。
- 比例超出引擎支持范围时（例如 agy 选了 21:9、API 超过 3:1），用最接近的比例并告诉用户。
- OpenAI API 花的是用户自己的钱：只在用户选了它或点名时使用。其他途径失败或额度用完时，不要自动改用 API，先问用户。
- 在 Codex 端没有这个面板工具：用一句话列出默认选择（Codex 内置生图、比例按需求），用户不改就直接生成。

## 第二步：按选择执行
| 途径 | 怎么跑 |
|---|---|
| GPT Image 2.6 · OpenAI API | `scripts/gen.sh -e api`，面板选择按下表换成参数；配置 Key、全部参数、报错见 [references/openai-api.md](references/openai-api.md) |
| GPT Image · Codex | `scripts/gen.sh -e gpt`（见下方「调用」） |
| Nano Banana 2 · agy | `scripts/gen.sh -e nb` |
| 选了多个命令行途径 | 用逗号合成一条命令一起跑，如 `-e api,nb`、`-e gpt,api,nb`（`all` = 三个都跑） |
| GPT Image · ChatGPT 网页 | 浏览器步骤见 [references/chatgpt-web.md](references/chatgpt-web.md)，只在 Claude 端可用 |
| Nano Banana 2.1 · AI Studio | 浏览器步骤见 [references/aistudio.md](references/aistudio.md)，只在 Claude 端可用 |

面板选择 → OpenAI API 参数：

| 面板 | API 参数 |
|---|---|
| 分辨率 1K / 2K / 4K | `-r 1K` / `-r 2K` / `-r 4K`（16:9 分别为 1360×768 / 2560×1440 / 3840×2160） |
| 思考强度 最高 | `-m sunburst -c high` |
| 思考强度 中等 | `-m sunburst -c medium` |
| 思考强度 最快 | `-m flare -c low` |

- `sunburst` / `flare` 会展开成 `.env` 里默认模型同一代的型号（默认 2.6：`gpt-image-2.6-sunburst` / `gpt-image-2.6-flare`）。用户点名具体型号（如 2.5、`gpt-image-2`）时直接 `-m <型号>`。
- 质量默认 `high`（`.env` 可改）。用户要「画质拉满」时加 `-q xhigh` 或 `-q max`，要「便宜 / 先出草稿」时加 `-q medium` 或 `-q low`。
- 透明背景（Logo、贴纸、抠图素材）只有 API 能直接出：加 `-b transparent`（会自动用 png）。
- 局部重绘：`-i 原图 -M 蒙版.png`。蒙版是与原图同尺寸、带透明通道的 PNG，透明处就是要改的区域。
- 改图想保持原图比例时，API 途径不传 `-a`，会沿用第一张参考图的比例。

多选时：命令行途径（Codex / API / agy）合成一条命令用 `run_in_background` 先跑起来，同时做浏览器途径；两个浏览器途径之间依次做（共用一个 Chrome）。全部完成后一起交付，并注明每张图来自哪个途径、用了什么参数。

Codex 和 ChatGPT 网页这两个订阅途径都不能指定 Sunburst / Flare 或尺寸，由 OpenAI 自动决定；要指定模型和尺寸请用 OpenAI API 途径。

## 调用
```bash
bash <skill-root>/scripts/gen.sh -e api -a 16:9 -r 2K -m sunburst -c high -p "<提示词>" [-i 参考图.png ...] [-o 输出目录] [-n 张数] [-t 文件名前缀]
bash <skill-root>/scripts/gen.sh -e gpt -a 9:16 -p "<提示词>" [-i 参考图.png ...] [-o 输出目录] [-n 张数] [-t 文件名前缀]
```
- `-e` 途径：`gpt`（Codex）、`api`（OpenAI API）、`nb`（agy），可以用逗号组合；`both` = `gpt,nb`，`all` = `gpt,api,nb`。
- `-a` 比例：`1:1`（默认）`16:9` `9:16` `4:3` `3:4`；API 还支持 1:3 到 3:1 之间的任意比例（如 `21:9`、`3:2`）和 `auto`。
- `-i` 参考/待改图，可重复；必须是磁盘上的文件路径。用户在对话里贴的图如果没有路径，请用户给出文件路径。API 只收 png/jpg/webp（单张 < 50 MB，最多 16 张），iPhone 的 HEIC 先用 `sips -s format jpeg` 转换。
- `-o` 默认 `~/Pictures/AI生图/`；用户在某个项目里工作且说"放到项目里"时用项目内目录。
- `-n` 每个途径的张数，并行生成（API 一次请求最多 10 张，超过自动分批）。
- 只对 API 生效：`-r` 分辨率、`-m` 模型、`-q` 质量、`-c` 规划强度、`-b` 背景、`-f` 格式（png/jpeg/webp）、`-M` 蒙版。更多选项（`-s 宽x高`、`--markup` 标注图、`--moderation`、`--dry-run` 预览请求）直接用 `scripts/openai_image.py`，见 [references/openai-api.md](references/openai-api.md)。
- 提示词直接用用户的语言写清楚：主体、场景、风格、构图、要出现的文字（用引号标出原文）。用户给的描述太简略时可以帮着补全，但不要改掉用户点名的要素。

**Bash 调用必须设 `timeout: 600000`**：单张 GPT（Codex）约 1–2 分钟，Nano Banana 约 1–3 分钟；API 的 Flare 最快几秒，Sunburst、4K 或 `max` 质量更慢，可能要几分钟。多个途径、`-n` ≥ 3 或 API 4K 时用 `run_in_background`，结束后会收到通知。

## 输出与交付
- 脚本每张图打印一行 `SAVED: <路径> (<宽>x<高>)`；全部失败时退出码为 1，并在 stderr 打印日志位置和末尾几行。API 途径失败时会打印报错原文和 `HINT:` 处理建议。
- API 途径成功时 stderr 有一行 `api: <模型> | <尺寸> | quality=… | …`，交付时把模型、尺寸、质量告诉用户。
- 拿到路径后先查看图片、确认符合要求，再交给用户：
  - **Claude**：用 Read 查看（4K 大图先用 `sips -Z 1600` 生成预览再看），再用 SendUserFile（`display: render`）发图，并附上保存路径。
  - **Codex**：用本地图片查看能力检查后，在回复里给出保存路径。
- 改图迭代：把上一张输出作为 `-i` 再跑一次。

## 在 Codex 里使用
Codex 自带 GPT Image 生图：用户要「GPT Image · Codex」时，直接用内置生图工具，生成后把文件复制到输出目录，不要通过本脚本再套一层 `codex exec`。本脚本在 Codex 里用 `-e api` 和 `-e nb`：
- `-e api` 要联网：被沙箱拦截时，请用户批准该命令越过沙箱运行。Key 填在 `.env` 里，因为 Codex 可能会过滤名字里带 KEY 的环境变量。
- 如果 agy 因沙箱无法联网或无法写 `~/.gemini`，同样请用户批准该命令越过沙箱运行。

ChatGPT 网页和 AI Studio 两个途径依赖 Claude in Chrome，Codex 端不可用；用户在 Codex 里要用它们时，请他到 Claude 里生成。

## 须知
- 分辨率：OpenAI API 按 1K/2K/4K 指定，最高 3840×2160（超过 2560×1440 属实验性）；Codex 和 ChatGPT 网页固定约 1672×941（16:9）/ 941×1672（9:16），提示词里要求 4K 也不变；agy 的 Nano Banana 2 约 1376×768；AI Studio 的 Nano Banana 2.1 能出 2K/4K（最高 5504×3072）。
- 额度与费用：Codex、ChatGPT 网页用 ChatGPT 订阅额度，agy、AI Studio 用 Google 账号额度，不额外花钱；OpenAI API 按 token 计费，记在用户自己的 OpenAI 账户（粗估见 [references/openai-api.md](references/openai-api.md#费用粗估)）。额度用尽或余额不足时如实转告用户，不要自动换成别的付费途径。
- API Key：不要读取、打印或回显 `.env`，不要把 Key 放进命令行参数。缺 Key 时把 `<skill-root>/.env` 的完整路径告诉用户，请用户自己填写，不要让用户把 Key 发到对话里。
- 脚本以只读沙箱运行 Codex（`-s read-only`）、以 `--sandbox` 运行 agy，**不要**加 `--dangerously-skip-permissions` / `--dangerously-bypass-approvals-and-sandbox`。

## 故障排查
| 现象 | 处理 |
|---|---|
| `Codex CLI not found` | 装 ChatGPT/Codex 桌面版，或 `npm i -g @openai/codex` 后运行 `codex login` |
| Codex 报未登录 | 让用户在终端运行 `codex login`（浏览器登录 ChatGPT） |
| `Antigravity CLI not found` | `curl -fsSL https://antigravity.google/cli/install.sh \| bash` |
| agy 要求登录 / 无模型 | 让用户在终端运行一次 `agy`，选 Google OAuth 登录 |
| agy 提示 quota / limit | Nano Banana 额度用完，改用 `-e gpt` 或等额度刷新 |
| `no OpenAI API key configured` | 请用户编辑 `<skill-root>/.env`（没有就先 `cp .env.example .env`）填上 `OPENAI_API_KEY`，再运行 `python3 <skill-root>/scripts/openai_image.py --check` 自检（免费） |
| API 报 401 / 403 / 404 / 429 / 400 等 | 按输出里的 `HINT:` 处理，对照表见 [references/openai-api.md](references/openai-api.md#报错对照) |
| `python3 not found` | macOS 运行 `xcode-select --install` |
| 没有 SAVED 输出 | 查看 stderr 给出的日志目录里的 `log.jsonl` / `log.txt` |
