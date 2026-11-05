# OpenAI API 途径（GPT Image 2.6 / 2.5 / 2，用户自己的 API Key）

调用 OpenAI 官方 Images API：没有参考图时请求 `POST /v1/images/generations`，带 `-i` 时请求 `POST /v1/images/edits`。实现是 `scripts/openai_image.py`（只用 Python 标准库，macOS 自带的 python3 就能跑），`scripts/gen.sh -e api` 会调用它。Claude 和 Codex 都能用，全自动，不需要浏览器。

## 首次配置（用户自己填 Key）
1. 在 https://platform.openai.com/api-keys 创建 API Key，并在 Billing 页面充值（ChatGPT 会员不含 API 额度）。
2. GPT Image 模型要求组织先完成验证：Settings → Organization → General → **Verify Organization**，通过后约 15 分钟生效。
3. 在 skill 目录里复制模板，再用编辑器把 Key 填在 `OPENAI_API_KEY=` 后面（`.env` 已在 `.gitignore` 里，不会被提交）：
   ```bash
   cd <skill-root> && cp .env.example .env && chmod 600 .env
   ```
4. 自检（不生图、不花钱，会检查 Key 是否有效、默认模型能否使用）：
   ```bash
   python3 <skill-root>/scripts/openai_image.py --check
   ```

读取规则：
- `.env` 里填了 `OPENAI_API_KEY` 时，连接设置（Key、`OPENAI_BASE_URL`、`OPENAI_ORG_ID`、`OPENAI_PROJECT_ID`、`HTTPS_PROXY`）只看 `.env`，系统环境变量里的同名设置不会混进来。
- `.env` 没填 Key 时，才使用系统环境变量 `OPENAI_API_KEY`（以及 `OPENAI_BASE_URL` 等）。
- 默认参数（`OPENAI_IMAGE_MODEL`、`OPENAI_IMAGE_QUALITY`、`OPENAI_IMAGE_RESOLUTION` 等）依次取：命令行 → `.env` → 环境变量 → 内置默认。
- 需要代理才能访问 api.openai.com 时，在 `.env` 里填 `HTTPS_PROXY=http://127.0.0.1:7890`（HTTP 代理端口，不支持 socks5）。不填时沿用环境变量里的代理；macOS 上还会读取系统代理设置。

给 Agent 的规则：
- 不要读取、打印或回显 `.env` 的内容，不要把 Key 写进命令行参数或日志；脚本自己读取 Key，输出里只显示 `sk-proj-...末4位`。
- 缺 Key 时，把 `.env` 的完整路径告诉用户，请用户自己填写，**不要让用户把 Key 发到对话里**。如果用户已经在对话里贴了 Key 并要求代填，可以写进 `.env`（不要回显），同时提醒用户这个 Key 已出现在对话记录里，用完最好到后台轮换。
- 报错时按脚本输出的 `HINT:` 处理。模型暂不可用时可以改用 2.5 同款并告诉用户；不要为了绕过安全拦截自行改 `--moderation low`，也不要自动换成别的付费途径。

## 模型
| 模型 | 说明 |
|---|---|
| `gpt-image-2.6-sunburst`（默认） | 2026-11-04 发布。质量优先，细节更好，多轮修改的一致性更好 |
| `gpt-image-2.6-flare` | 同期发布。速度优先，最快约 6 秒出图 |
| `gpt-image-2.5-sunburst` / `gpt-image-2.5-flare` | 上一代（2026-09-08），2.6 暂时用不了时的备选 |
| `gpt-image-2` | 2026-04-21 发布的第一代 GPT Image 2 |
| `gpt-image-1.5` / `gpt-image-1-mini` | 旧型号，只支持 1024×1024 / 1536×1024 / 1024×1536 三种尺寸 |

`gpt-image-1` 已于 2026-10-23 下线，DALL·E 2/3 已于 2026-05-12 退役。

`-m` 可以写完整型号，也可以写简写：`sunburst` / `flare` 展开成 `.env` 默认模型同一代的型号（默认 2.6）；`2.5-flare` 这种会自动补上 `gpt-image-` 前缀。

## 尺寸
`-r 1K / 2K / 4K` 分别按约 1024×1024、2560×1440、3840×2160 的像素量换算，任何比例的像素量都差不多，宽高取 16 的倍数：

| 比例 | 1K | 2K | 4K |
|---|---|---|---|
| 1:1 | 1024×1024 | 1920×1920 | 2880×2880 |
| 16:9 | 1360×768 | 2560×1440 | 3840×2160 |
| 9:16 | 768×1360 | 1440×2560 | 2160×3840 |
| 4:3 | 1168×880 | 2208×1664 | 3312×2480 |
| 3:4 | 880×1168 | 1664×2208 | 2480×3312 |
| 3:2 | 1248×832 | 2336×1552 | 3520×2352 |
| 2:3 | 832×1248 | 1552×2336 | 2352×3520 |
| 21:9 | 1568×672 | 2912×1248 | 3840×1648 |

- 比例限 1:3 到 3:1，超出时按最接近的比例生成，并在 stderr 提示。
- 超过 2560×1440 的尺寸 OpenAI 标为实验性（更慢、效果波动更大），所以 4K 都属实验性；上限 3840×2160。
- 也可以直接指定 `-s 1536x1024`，或 `-s auto` 让模型决定。
- 改图时不传 `-a`，会沿用第一张参考图的比例（会考虑 JPEG 的 EXIF 方向）。

## 参数
| 参数 | 取值 | 说明 |
|---|---|---|
| `-q` 质量 | `low` / `medium` / `high`（默认）/ `xhigh` / `max` / `auto` | 渲染细节，越高越慢越贵 |
| `-c` 规划强度（complexity） | `low` / `medium` / `high` | 出图前的规划（"思考"）强度，和渲染质量无关；不传就用模型默认值。改背景、换个字这类小改动用 `low` 更稳，文字多、版面复杂、物体多时用 `medium` / `high`。模型不认这个参数时，脚本会去掉它自动重试 |
| `-b` 背景 | `auto` / `opaque` / `transparent` | 透明背景需要 png 或 webp，脚本会自动改成 png |
| `-f` 格式 | `png`（默认）/ `jpeg` / `webp` | `gif`、`svg` 需要账号有预览权限 |
| `--compression` | 0–100 | 只对 jpeg / webp 生效 |
| `--moderation` | `auto`（默认）/ `low` | `low` 是较宽松的内容过滤，只在用户明确要求时用 |
| `-M` / `--mask` | PNG | 局部重绘：与第一张 `-i` 同尺寸、带透明通道，透明处是要改的区域，< 4 MB |
| `--markup` | PNG | 叠在第一张图上的透明标注图（圈、箭头、文字），用来指示怎么改；不能和蒙版同用 |
| `-n` | 张数 | 一次请求最多 10 张，超过自动分批 |
| `--timeout` | 秒 | 单次请求最长等待，默认 600 |
| `--dry-run` | — | 只打印将要发送的请求（不含 Key），不发送、不计费 |

参考图：png / jpg / webp，单张 < 50 MB，最多 16 张。iPhone 的 HEIC 先转换：`sips -s format jpeg 原图.heic --out 原图.jpg`。

直接调用示例（`python3 scripts/openai_image.py --help` 看全部参数）：
```bash
python3 <skill-root>/scripts/openai_image.py -p "<提示词>" -a 21:9 -r 4K -q xhigh -o <输出目录>
python3 <skill-root>/scripts/openai_image.py -p "<怎么改>" -i 原图.png --markup 标注.png -m sunburst -c low
```

## 费用粗估
按 token 计费，费用记在用户自己的 OpenAI 账户，以[官方价格页](https://openai.com/api/pricing)为准。第三方按官方计算器估算（2026-11）：2.6 的 1024×1024 单张约 low $0.025、medium $0.043、high $0.053、max $0.21；费用大致随像素量增长，2K 约为 1K 的 3.5 倍，4K 约 8 倍。Flare 和 Sunburst 单价相同，参考图另按图像输入 token 计费。用量和账单在 https://platform.openai.com/usage 查看。

## 报错对照
| 现象 | 处理 |
|---|---|
| `no OpenAI API key configured` | 请用户填 `.env`（见上方「首次配置」） |
| HTTP 401 `invalid_api_key` | Key 填错、没复制完整或已撤销：请用户重新复制 |
| HTTP 403 `organization must be verified` | 到 Settings → Organization → General 点 Verify Organization，通过后约 15 分钟生效 |
| HTTP 403 `unsupported_country_region_territory` | 当前出口地区不受支持：在 `.env` 里配置受支持地区的 `HTTPS_PROXY` |
| HTTP 403 其他 | 受限 Key 要开启 Images 写权限；项目要允许使用该模型 |
| HTTP 404 `model_not_found` | 账号还不能用这个模型：改用 `-m gpt-image-2.5-sunburst`（或 `gpt-image-2.5-flare`），并告诉用户 |
| HTTP 429 `insufficient_quota` | 余额不足或达到预算上限：请用户到 Billing 充值或调高上限；不要自动换途径 |
| HTTP 429 其他 | 速率限制，脚本已自动重试 2 次；稍后再试或减少 `-n` |
| HTTP 400 `moderation_blocked` | 被安全系统拦截：调整措辞或换参考图 |
| HTTP 400 提到 size / quality | 这个模型不支持该尺寸或质量：改 `-r 2K`、`-q high`，或换 2.5 |
| `no response ... within 600s` | 4K / max 太慢：加大 `--timeout` 或降低分辨率/质量；这张图可能已经计费，不要反复重跑 |
| `cannot resolve` / `connection refused` | 网络或代理问题：检查代理是否开着，或在 `.env` 填 `HTTPS_PROXY` |
| `CERTIFICATE_VERIFY_FAILED` | python.org 安装的 Python：运行 `/Applications/Python 3.x/Install Certificates.command`，或 `pip3 install certifi` |
| `SOCKS proxies ... not supported` | 把 `HTTPS_PROXY` 改成代理的 HTTP 端口（如 Clash 的 `http://127.0.0.1:7890`） |
