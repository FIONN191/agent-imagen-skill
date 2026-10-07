# ChatGPT 网页引擎（GPT Image，可选思考强度）

通过 Claude in Chrome 操作用户已登录的 chatgpt.com。只在 Claude 端可用。

## 账号
- 当前连接的 Chrome（Browser 1）登录的是 **Business** 账号。它的「选择模型」菜单里有 Latest / GPT-5.6 Sol / GPT-5.5，**Pro 是灰色、不能选**。
- Pro 账号在另一个 Chrome 配置里，暂时没连接。以后用户连上时，用 `list_connected_browsers` 和 `select_browser` 切换，在「选择模型」里选 Pro。
- 网页端出图实测 1672×941（16:9），在提示词里要求 4K 也不变（2026-10-08，Business）。思考强度只影响提示词的改写和构图质量，不影响分辨率。

## 思考强度（滑块 0–3）
| 值 | 名称 |
|---|---|
| 0 | Instant |
| 1 | Medium |
| 2 | High |
| 3 | Extra High（用户平时的默认值） |

这个设置会保存为用户的账号偏好：改之前先记下原值，生成结束后改回去。

## 步骤
1. `tabs_context_mcp(createIfEmpty: true)`，在自己的标签页打开 `https://chatgpt.com/`（新对话）。
2. 设置思考强度：点击输入框右侧的按钮「选择 ChatGPT 模型」（按钮文字是当前档位，比如 Extra High）。弹层打开后：
   - 用 javascript_tool 运行 `document.querySelector('[role="slider"]').focus()`；
   - 用 `computer` 的 `key` 按 Left / Right 调档；
   - 读取 `[role="status"]` 里形如「High，第 3 项，共 4 项。」的文字，确认档位正确；
   - 按 Escape 关闭弹层。
   弹层失去焦点会自己关掉：打开后不要先做别的操作（比如调用 find），直接聚焦滑块。
3. 参考图：点输入框左侧的「+」，用 `find` 找到文件 input，再用 `file_upload` 上传。
4. 用 `find` 找到输入框「询问 ChatGPT」，点击后输入：`生成一张图片，比例 <比例>：<提示词>`，按 Return 发送。
5. 等待：每 10 秒检查一次，约 60–120 秒。用下面的代码检查是否出图（`已生成图像` 的数量增加、停止按钮消失即表示完成）：
   ```js
   [...document.querySelectorAll('img')].filter(i=>i.naturalWidth>400&&/已生成图像|Generated image/.test(i.alt))
     .map(i=>({w:i.naturalWidth,h:i.naturalHeight}))
   ```
6. 取最后一张生成图，按正常方式下载（用户这次的生图请求本身就是下载许可；不要把图片数据传到别处）：
   ```js
   const imgs=[...document.querySelectorAll('img')].filter(i=>i.naturalWidth>400&&/已生成图像|Generated image/.test(i.alt));
   const img=imgs[imgs.length-1]; const blob=await fetch(img.src).then(r=>r.blob());
   const ext=(blob.type.split('/')[1]||'png').replace('jpeg','jpg'); const name='<时间戳>-chatgpt-<档位>.'+ext;
   const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=name;
   document.body.appendChild(a); a.click(); a.remove(); ({name,w:img.naturalWidth,h:img.naturalHeight,type:blob.type})
   ```
7. 会弹出 Chrome 保存框，请用户点「存储」；同时运行 `bash <skill-root>/scripts/collect.sh '<name>' [输出目录]`（Bash `timeout: 600000`）。
8. 把思考强度改回原值，关闭自己开的标签页，再按 SKILL.md 的方式交付图片。
