# AI Studio 引擎（Nano Banana 2.1，可选分辨率和思考强度）

通过 Claude in Chrome 操作用户**已登录的** Chrome 里的 Google AI Studio Playground。只在 Claude 端可用（需要 `mcp__claude-in-chrome__*` 工具，按服务器说明一次性批量加载）。

AI Studio 界面说明：不选 API Key 时，网页端使用免费（tooltip 原文："Usage in AI Studio UI is free of charge when no API key is selected"）。Run 按钮在输入框为空时会显示 "This model requires a paid API key"，有内容后可正常运行（2026-10-08 实测）。如果有提示词时 Run 仍不可用、或提示需要付费 Key，**停下来告诉用户**，不要去选择或创建 API Key。

## 参数
| 项 | 可选值 |
|---|---|
| Aspect ratio | Auto 1:1 9:16 16:9 3:4 4:3 3:2 2:3 5:4 4:5 21:9 4:1 1:4 |
| Resolution | 1K 2K 4K（16:9 时 4K = 5504×3072） |
| Thinking level | Minimal Medium High |

用户没指定时：比例按需求选，分辨率 2K，思考 Medium。

## 步骤
1. `tabs_context_mcp(createIfEmpty: true)`，在自己的标签页打开 `https://aistudio.google.com/prompts/new_chat`。每张新图都开一个新对话；连续改同一张图时留在原对话里继续发。
   - 显示错误页（网络/代理不稳定）：等几秒重试；连续失败就告诉用户检查代理。用户说已有打开的 AI Studio 标签页时，可以请用户把它拖进 Claude 的标签组。
2. 截图确认右侧 Run settings 的模型是 **Nano Banana 2.1**（gemini-nano-banana-2.1）。不是的话，点模型卡片切换。
3. 设置参数：用 `find`/`read_page` 找到 combobox "Aspect ratio" / "Resolution" / "Thinking Level"，点开后用 `read_page(ref_id=<listbox>)` 读出选项再点。**每选一项设置面板都会滚动，必须重新获取 ref 或重新截图，不能复用旧坐标。** 全部设好后截图核对一遍。
4. 有参考图时：点 "Insert images, videos, or files"，用 `find` 找到文件 input，再用 `file_upload` 上传（单次总计 < 10 MB）。不要直接点系统文件选择框。
5. 点击输入框 "Enter a prompt"，输入提示词，点 Run。等待：4K + High 约 60–90 秒。每 10 秒检查一次，直到 Run 按钮恢复、并出现生成的图片。
6. 取图：页面里可能还有思考过程中的 1K 中间图，要选面积最大的 `blob:` 图片。用 javascript_tool 运行：
   ```js
   const img=[...document.querySelectorAll('img')].filter(i=>i.src.startsWith('blob:')&&i.naturalWidth>500)
     .sort((a,b)=>b.naturalWidth*b.naturalHeight-a.naturalWidth*a.naturalHeight)[0];
   const blob=await fetch(img.src).then(r=>r.blob());
   const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='<文件名>.jpg';
   document.body.appendChild(a); a.click(); a.remove();
   ({w:img.naturalWidth,h:img.naturalHeight,size:blob.size})
   ```
   文件名用 `<时间戳>-nb21-<分辨率>.jpg`。用户这次的生图请求本身就是下载这张图的许可；**只用 Chrome 的正常下载**，不要把图片数据传到别处（localhost、其他网站），也不要改 Chrome 设置。
7. 用户的 Chrome 开着「下载前询问保存位置」时会弹出系统保存框，Claude 操作不了。请用户点「存储」（保存位置随意），同时运行：
   ```bash
   bash <skill-root>/scripts/collect.sh '<文件名>.jpg' [输出目录]
   ```
   Bash `timeout` 设为 `600000`。脚本会在 Chrome 默认下载目录、下载、文稿、桌面里等这个文件出现（最多 5 分钟），然后移到输出目录，打印 `SAVED:`。用户如果不想每次都点，可以自己在 Chrome 设置里关掉「下载前询问每个文件的保存位置」。
8. 交付方式与其他引擎相同：用 Read 查看图片（4K 大图先用 `sips -Z 1600` 生成预览再看），再用 SendUserFile 发图，附上保存路径。全部完成后关闭自己开的标签页。
