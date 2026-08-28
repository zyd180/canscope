# CANScope · CAN 总线分析仪

基于 **BLF 日志 + DBC 数据库** 的 CAN/CAN FD 总线离线分析工具,Python 原生桌面应用。
由 Web 版(`blf-dbc-web`)迁移而来:**零浏览器、零部署、开箱即用**。

当前版本 **v1.0.0**(首个正式版)· 变更历史见 [CHANGELOG.md](CHANGELOG.md);
迁移方案与里程碑见 [PLAN.md](PLAN.md)。

## 功能

| 模块 | 功能 |
|---|---|
| 文件 | 打开 .blf/**.asc**/**.mf4**/.dbc/.log/.txt(类型按内容魔数识别,改名文件也能打开);多选时 DBC 按通道顺序映射;后台解析带进度条;工程自动记忆 |
| 报文树 | 通道分组 → 报文(ECU 彩色标签/无数据灰色删除线)→ 信号;实时搜索;**未识别报文灰组**(DBC 未定义 ID,右键一键生成 DBC 骨架) |
| 示波器 | 多窗纵向堆叠(最多 64 信号/20 色);值表信号自动阶梯线;chip 单窗增删;每窗可独立关闭(自动重编号);**底部缩略导航条**(全时长轮廓 + 视窗框) |
| 量程控制 | 每窗独立:**双击绘图区**在 自动适应 ↔ 手动锁定 间切换,或右键输入精确 min/max 锁定;标题栏实时显示锁定范围 |
| 区间框选统计 | `Ctrl+左键拖拽`选时间区间:条带高亮 + 统计浮层(min/max/mean/std 或值表状态分布);可一键应用到信号统计页作为时间过滤 |
| 曲线显隐 | 点击窗口内信号**图名**临时隐藏/恢复该曲线(不重新解码);隐藏态跨刷新保持;右键「显示全部曲线」一键还原 |
| 交互 | 滚轮缩放(以鼠标为中心,最小窗 0.5s,钳制不越界)、Shift+滚轮滚动页面、拖拽平移、跨窗光标读数 + 同步竖线、**Shift+单击锚点测量(Δt/频率)**、右键全中文菜单、重置缩放 |
| 图像导出 | 右键「导出本窗图像 PNG」:整窗截图并附时间范围/量程模式水印 |
| 回放 | CANoe 式 ▶/⏸/⏹、进度拖拽 seek、0.5~10x 变速、x 轴固定生长式绘制、诊断行(帧数/点数/耗时) |
| Trace | 报文帧表格,分页 200/页,信号值搜索(数值容差/状态名),按当前缩放区间过滤,**全量导出 CSV** |
| 统计 | ID 分布条形图 + Bus Load 负载率;信号 min/max/mean/std/超范围;周期/抖动峰峰/丢帧估计;抖动峰值图上标记 |
| 导出 | 当前报文全信号 CSV(UTF-8 BOM,Excel 直开);**BLF 片段**(按缩放区间裁剪,供 CANoe 复现);Trace 全量 CSV;**DBC 骨架**(未知 ID → 可编辑起步文件) |
| 记忆 | 选中信号三态恢复(首次自动选/有记录恢复/清空保持)、抖动开关(INI 文件,随应用目录) |

## 快速开始

### 方式一:免安装运行(推荐)

```text
CANScope/
├── CANScope.exe   ← 双击即用
├── data/             ← 可选:放入 .blf/.dbc
└── config/           ← 运行时自动生成(界面偏好)
```

首次使用:菜单「生成演示数据」一键体验,或 `Ctrl+O` 同时选择你的 `.blf` 与 `.dbc`
(CAN FD 多通道按通道顺序依次选中各 DBC;后续可在「配置」弹窗中重新映射)。

### 方式二:源码运行

```bash
pip install -r requirements.txt
python main.py            # 源码运行
python scripts/make_test_data.py   # 可选:生成演示数据
```

要求:Python ≥ 3.9,Windows(理论跨平台,未验证)。

## 操作说明

| 操作 | 方式 |
|---|---|
| 打开文件 | `Ctrl+O` 或工具栏;类型按内容识别(.blf/.asc/.mf4/.dbc/.log/.txt 均可;MF4 需可选依赖 asammdf) |
| 折叠报文树 | 树与主界面之间的窄条 `◀/▶`:向左折叠后右侧界面整体扩展 |
| 绘制曲线 | 点击左侧树中信号;再次点击移除;同一信号可复制到多个示波器 |
| 缩放 | **滚轮**(或 Ctrl+滚轮)以鼠标为中心缩放;最小窗 0.5s;「重置缩放」恢复全量 |
| 滚动页面 | `Shift+滚轮`(多窗纵向浏览) |
| 平移 | 左键拖拽 |
| 光标读数 | 悬停任意示波器:全窗同步竖线,侧栏「光标」列显示各信号该时刻值 |
| 锚点测量 | `Shift+单击` 设/清锚点:全窗红线,侧栏「锚点」列常驻显示各信号锚点时刻值,状态栏显示 `锚点 · Δt (频率)` |
| 锁定 Y 轴 | 双击绘图区切换 自动 ↔ 锁定(取当前视图);右键「锁定 Y 轴…」可输入精确范围;再次双击恢复自动 |
| 区间框选统计 | `Ctrl+左键拖拽` 松开即出统计浮层;右键「应用本窗统计区间 → 统计页」联动过滤统计表,「清除本窗统计区间」撤销;进入回放时自动清空 |
| 曲线显隐 | 点击窗口内图名(色点+名称,手型光标)临时隐藏/恢复;右键「显示全部曲线」一键还原;隐藏态跨刷新保持 |
| 导航条 | 示波器列底部:拖动中部平移视窗、拖两侧边缘改跨度、滚轮缩放;与主图缩放双向同步(播放中锁定) |
| 导出图像 | 右键「导出本窗图像 PNG…」,附加 CANScope 水印行 |
| 导出片段 BLF | 工具栏「导出片段 BLF」:按当前缩放区间裁剪独立 BLF(片段时间轴从 0 起算,相对时序与原日志一致) |
| Trace 全量导出 | Trace 页「导出全部 CSV」:当前报文在相同信号值过滤/时间区间下的全部帧,列与表格一致 |
| 生成 DBC 骨架 | 右键树中「未识别报文」组或条目:按观测 ID+DLC 生成无信号定义的 DBC;编辑补全后可在「配置」中映射使用 |
| 右键菜单 | 示波器内右键:添加信号… / 重置缩放 / 清除测量锚点 / 清除本窗信号 / 关闭本示波器 |
| 窗口管理 | 示波器标题栏「+信号」复制信号入窗、`✕` 关闭本窗;侧栏 `+` 新建窗、`−` 删末窗、`清` 清空全部信号 |
| 回放 | 选中信号后点 ▶;进度条拖拽定位;变速即时生效;播放中修改信号集会自动停止 |
| 配置 | 工具栏「配置」弹窗:总线类型/波特率(影响 Bus Load)、通道 DBC 重映射、抖动峰值标记 |
| 导出 | 工具栏「导出 CSV」,导出首个已选信号所属报文的全部信号(按当前缩放区间) |
| 外观 | 深色主题 + Windows 深色标题栏/边框(DWM 匹配主题色,Win10 19041+/Win11);启动默认最大化 |

## 目录结构

```text
canscope/
├── main.py                  # 入口(含 --smoke 打包冒烟)
├── core/                    # 纯业务逻辑(零 UI 依赖,自 Web 版迁移)
│   ├── blf_cache.py         #   帧 LRU 索引缓存(支持进度回调)
│   ├── blf_parser.py        #   日志流式统计(BLF/ASC/MF4,含按通道 ID+DLC 清单)
│   ├── log_reader.py        #   日志读取器工厂(按内容识别 → can.Message 流)
│   ├── mdf_source.py        #   MF4/MDF4 CAN 总线日志适配(asammdf 可选依赖)
│   ├── dbc_parser.py        #   DBC 加载(UTF-8/GBK 编码检测)
│   ├── decoder.py           #   信号解码 + 均匀降采样
│   ├── file_types.py        #   文件类型按内容识别(BLF/MDF 魔数、DBC/ASC 文本特征)
│   ├── frame_source.py      #   帧源抽象 + 堆合并回放源
│   └── playback.py          #   回放引擎
├── services/                # 统计/导出/配置/演示数据
├── controller/              # AppState 中央状态 + 回放控制器
├── workers/                 # 线程池任务/BLF 后台加载(进度节流)
├── gui/                     # PySide6 界面
│   ├── main_window.py       #   主窗口装配
│   ├── message_tree.py      #   报文/信号树
│   ├── scope_plot.py        #   单示波器(缩放/平移/锚点/右键菜单)
│   ├── scope_stack.py       #   多窗管理/x 轴同步/右键菜单
│   ├── signal_sidebar.py    #   已选信号侧栏(锚点值+光标值双列)
│   ├── playbar.py           #   播放控制条
│   ├── trace_panel.py       #   Trace 报文流
│   ├── id_stats_panel.py    #   ID 统计 + Bus Load
│   ├── sig_stats_panel.py   #   信号统计 + 周期抖动
│   ├── config_drawer.py     #   配置弹窗(QDialog)
│   ├── palette.py / theme.py#   调色板 / 深色主题 QSS
├── scripts/                 # 测试数据/图标/构建脚本
├── tests/                   # 冒烟测试(9 套,含真实大文件可选验证)
├── assets/                  # 应用图标
├── data/                    # 运行时:config.json / 演示数据
└── config/                  # 运行时:界面偏好(INI)
```

## 测试

```bash
python tests/smoke_core.py        # 核心逻辑 17 项(解析/解码/统计/回放)
python tests/smoke_sync.py        # Web v113 同步项(类型识别/进度回调;SYNC_REALDATA=1 加测 449MB 真实文件)
python tests/smoke_gui.py         # M2 图表交互 22 项
python tests/smoke_m3.py          # M3 数据页签 15 项
python tests/smoke_m4.py          # M4 回放 16 项
python tests/smoke_m5.py          # M5 配置/记忆/映射 21 项
python tests/smoke_scope_ops.py   # 示波器窗口操作 7 项(含图形泄漏检测)
python tests/smoke_r1.py          # R1 图表与分析补强 24 项(Y锁/框选统计/minimap/显隐/PNG)
python tests/smoke_r2.py          # R2 数据互通 21 项(ASC/MF4 往返/片段/Trace 全量/骨架)
python tests/smoke_r3.py          # R3 诊断/版本信息
python scripts/benchmark.py       # 解析/解码/负载性能与 Python 内存基准
python scripts/compat_check.py    # 当前 Python 环境依赖导入检查
python scripts/verify_package.py  # 检查 PyInstaller 产物必需文件
python tests/diag_click.py        # 树点击链路
python tests/realdata_gui.py      # 真实 449MB 数据 GUI 全流程(手动)
```

GUI 测试默认 offscreen 无头运行,也可 `$env:QT_QPA_PLATFORM='windows'` 真窗验证。

## 打包

```powershell
powershell -File scripts/build.ps1     # 产出 dist/CANScope/
dist\CANScope\CANScope.exe --smoke   # 打包冒烟(自动验证并截图,结果写 smoke_log.txt)
# 也可直接双击 build.bat 一键打包
```

用户手册见 [docs/USER_GUIDE.md](docs/USER_GUIDE.md)，程序内“快捷键”按钮可打开速查页。
合并到 `master` 后，CI 会按 `version.py` 自动创建版本 Tag 并发布 Release。
需要用本地内容覆盖 GitHub 时，可双击 `push_github.bat`；该脚本会执行强制推送。

## 技术栈

PySide6(Qt 6)+ pyqtgraph + python-can + cantools;
打包:PyInstaller(onedir)。
