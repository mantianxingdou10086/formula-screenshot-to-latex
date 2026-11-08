# 公式截图转 LaTeX（Windows）

常驻托盘的小工具。只在按下 **Ctrl+Alt+L** 时读取剪贴板截图，调用 OpenAI 兼容多模态 API，将识别出的 LaTeX 复制到剪贴板并显示确认小窗。

不提供历史记录、批量处理、离线 OCR、安装包或自制框选 UI。截图始终使用 Windows 自带 **Win+Shift+S**。

## 1. 安装依赖

Windows 10/11，Python **3.10 或更新版本**，需带 tkinter（python.org 的常规 Windows 安装包含它）。已在 Windows 11 / Python 3.13 实机验证。

在本目录打开 PowerShell：

```powershell
py -m pip install -r requirements.txt
```

项目直接第三方依赖仅 `Pillow`、`requests`、`keyboard`；requests 自身的传递依赖由 pip 安装。tkinter、ctypes 和其他模块均为标准库。托盘、原生右键退出菜单和剪贴板写入由 ctypes 调用 Windows API，不需要 pystray 或 pywin32。

## 2. 配置环境变量

必须配置以下三个变量；程序没有默认 API、没有内置密钥，也不读取 `.env` 文件。

| 变量 | 含义 |
| --- | --- |
| `FORMULA_API_BASE` | OpenAI 兼容 API 根地址，一般以 `/v1` 结尾 |
| `FORMULA_API_KEY` | API 密钥，仅从进程环境读取 |
| `FORMULA_MODEL` | 服务商实际支持**图片输入**的模型标识 |

例如根地址 `https://api.example.com/v1` 会请求 `https://api.example.com/v1/chat/completions`。不要把网页地址或完整 `/chat/completions` 填作根地址。

### 临时配置：不将密钥写进文件或命令历史

以下命令在 **PowerShell** 中执行。将地址和模型占位值改成你的服务商信息；密钥在隐藏输入提示中键入，不要写到脚本里。

```powershell
$env:FORMULA_API_BASE = 'https://api.example.com/v1'
$env:FORMULA_MODEL = '你的多模态模型标识'
$secret = Read-Host '输入 API key（隐藏输入）' -AsSecureString
$env:FORMULA_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
Remove-Variable secret
py main.py
```

变量仅对这个 PowerShell 及其子进程有效。退出工具后可执行：

```powershell
Remove-Item Env:FORMULA_API_KEY
```

### 开机启动需要的持久环境变量

在 Windows 搜索“**编辑账户的环境变量**”，在“用户变量”中添加上述三个变量。设置完成后，**注销并重新登录**，保证资源管理器和开机启动进程继承新环境。

注意：持久用户环境变量由 Windows 存在注册表中，并非加密密钥库；程序自身不会将密钥、截图或结果保存到文件。如果不希望密钥持久保存，请用上面的临时方式，并在每次登录后手动启动。不要将真实密钥提交到代码仓库、README、启动脚本、快捷方式参数或聊天中。远程 API 请使用 HTTPS；截图会发送给你指定的服务商。

## 3. 启动和使用

```powershell
py main.py
```

启动后不显示主窗口；通知区域出现通用应用图标，悬停提示“公式截图转 LaTeX · Ctrl+Alt+L”。图标也可能被 Windows 收在任务栏的 **^** 中。

1. 按 **Win+Shift+S**，框选一个公式。
2. 等待系统把截图写入剪贴板。
3. 按 **Ctrl+Alt+L**。
4. 等待 API 返回；成功后出现“已复制”小窗，显示纯 LaTeX 源码。
5. 关闭小窗或按 Esc，在目标位置按 **Ctrl+V**。

成功时先写回剪贴板，再弹窗确认，**不需要再点一次复制**。小窗显示源码，不负责渲染公式。KaTeX 的源码输入框直接粘贴；Markdown 编辑器若要求 `$...$` 或 `$$...$$`，由你在外层自行添加。

处理请求期间不重复发起请求。如果等待时复制了别的内容，本次结果不会覆盖新剪贴板，会提示重新截图。

### 退出

- **右键托盘图标 → 退出**；或
- 使用 `py main.py` 启动时，在它所属终端按 **Ctrl+C**。

不要重复启动多个实例，以免同一个热键触发多个请求。普通权限启动即可；若目标程序以管理员身份运行导致热键被拦，可尝试同级权限运行本工具。

## 4. 隐藏控制台和开机常驻

不需要安装包，也不会自动修改你的启动项。

1. 正确设置上述 Windows **用户环境变量**，注销后重新登录。
2. 在 PowerShell 执行以下命令，找到当前解释器旁的 `pythonw.exe`：

   ```powershell
   py -c "import pathlib,sys; print(pathlib.Path(sys.executable).with_name('pythonw.exe'))"
   ```

3. 按 **Win+R**，输入 `shell:startup`，打开当前用户启动文件夹。
4. 右键 → 新建 → 快捷方式，目标填写：

   ```text
   "第2步输出的完整pythonw.exe路径" "D:\小插件创作\main.py"
   ```

   若项目移动了，替换成实际的 `main.py` 绝对路径。快捷方式名称可填“公式截图转 LaTeX”。参数里**不要填写 API key**。

5. 双击快捷方式确认托盘图标出现。之后每次登录 Windows 都会常驻。

隐藏控制台模式下用托盘右键退出，没有终端可以按 Ctrl+C。取消开机启动只需删除该快捷方式。

## 5. 出错时的行为

| 情况 | 提示及剪贴板行为 |
| --- | --- |
| 没有截图（包括只有文字/文件列表） | **先用 Win+Shift+S 截图**；不调用 API，不改剪贴板 |
| 环境变量缺失 | 提示缺少的变量名；原图保留 |
| 请求超时 | 连接/读取超时参数为 **30 秒**；弹出超时提示，原图保留 |
| 网络/TLS/代理异常 | 网络失败提示；原图保留 |
| HTTP 401/403/404/429/服务错误 | 提示状态码及通用原因；原图保留 |
| 无效 JSON、响应结构不正确 | 响应格式提示；原图保留 |
| 空结果或模型输出被截断/拦截 | 提示未识别/截断；原图保留 |
| 剪贴板被其他程序锁定 | 复制失败提示，稍后重试 |

程序不自动重试请求，不自动切换模型，不将服务商原始响应/请求对象回显到日志，避免暴露密钥。内置提示词按任务原文保存；若模型仍附带代码块或数学外层定界符，会防御性剥除包装，不改公式正文。识别精度与模型、截图清晰度有关，尤其手写符号需要人工确认。

写入时在 Windows 剪贴板锁内复查版本，避免覆盖等待期间的新内容。清空前仅在内存备份原截图的 DIB/DIBV5 与纯文本；写入被 Windows 拒绝时尝试恢复。如果系统连恢复操作也拒绝，会明确提示重新截图，不能保证这种系统级双重故障下保留原图；应用专有的附加剪贴板格式不在回滚范围内。API 失败和空返回路径完全不执行清空或写入。

## 6. 测试与验收边界

附加目录 `tests/` 只用于测试，不是运行所需功能，测试仅使用三个第三方依赖及标准库。

```powershell
# 请求格式、无图校验、异常结果、Ctrl+C 信号退出等
py -m unittest discover -s tests -v

# 真实 Windows 剪贴板、全局热键、Tk 小窗、原生托盘菜单和本机 HTTP
py tests/windows_smoke.py
```

桌面集成测试会临时占用剪贴板、注入 Ctrl+Alt+L 并弹窗。请先保存重要剪贴板内容，测试期间不要使用键盘或剪贴板；测试会尽量恢复常见图片/纯文本，但不能承诺保留所有应用的专有剪贴板格式。超时测试会真实等待约 30 秒。

本机 HTTP 桩的五类 LaTeX 样例只用于验证源码传输和复制不损坏，**不代表真实模型识别成功**。程序不内置 KaTeX 或离线语法检测。真实服务的五图验收仍需配置你的多模态 API 后进行：

- 印刷体积分公式
- 手写极限公式
- 矩阵（检查行列与换行符）
- 带根号的分式（检查根号和分母范围）
- 含希腊字母的公式（检查相似字形）

每项均按“Win+Shift+S → Ctrl+Alt+L → 粘贴到 KaTeX”验收，同时检查数学含义与原图一致，而非只检查能否渲染。
