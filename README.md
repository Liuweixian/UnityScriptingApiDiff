# Unity Scripting API Diff

比较 [Unity 官方 Scripting API 文档](https://docs.unity3d.com/ScriptReference/index.html) 在不同版本之间的 **新增、移除、变更**，并生成交互式 HTML 报告。

## 原理

工具从 Unity 文档站抓取每个版本对应的 `docdata/toc.js`（完整 API 索引树），对比两个版本之间的条目差异：

| 层级 | 数据来源 | 速度 |
|------|----------|------|
| **类型级**（类、枚举、结构体等） | `toc.js` | 快（仅 2 次请求） |
| **成员级**（方法、属性等增删） | 各类的 ScriptReference 页面 | 较慢（约 3000+ 页面） |
| **签名级**（成员签名变更） | 各成员的 ScriptReference 页面 | 最慢 |

## 安装

```bash
cd UnityScriptingApiDiff
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 使用

### 列出可用版本

```bash
python main.py versions
```

### 快速对比（仅类型级增删）

```bash
python main.py diff --from 2021.3 --to 2022.3 -o report.html
```

### 深度对比（含成员增删）

```bash
python main.py diff --from 2021.3 --to 2022.3 --members -o report.html
```

### 完整对比（含成员签名变更）

```bash
python main.py diff --from 2021.3 --to 2022.3 --members --signatures -o report.html
```

### 同时输出 JSON

```bash
python main.py diff --from 2021.3 --to 2022.3 --json diff.json -o report.html
```

## 报告功能

生成的 HTML 报告包含：

- 新增 / 移除 / 变更数量统计
- 可搜索、可切换标签页浏览
- 每条 API 链接到对应版本的 Unity 官方文档
- 成员级变更展示新增/移除成员及签名对比

## 版本 URL 格式

Unity 文档按版本存放在不同路径，例如：

- `2022.3` → `https://docs.unity3d.com/2022.3/Documentation/ScriptReference/`
- `6000.3` → `https://docs.unity3d.com/6000.3/Documentation/ScriptReference/`
- `5.6` → `https://docs.unity3d.com/560/Documentation/ScriptReference/`

## 缓存

下载的数据会缓存在 `.cache/` 目录，重复运行会更快。使用 `--no-cache` 可强制重新下载。

## 限制

- 基于官方在线文档解析，需网络连接
- `toc.js` 仅包含类型级条目，不含每个方法的独立索引
- 成员签名对比依赖页面 HTML 结构，Unity 文档格式变化可能导致解析失效
- 与 [sttz/unity-api-diff](https://github.com/sttz/unity-api-diff)（反编译 DLL 对比）相比，本工具直接读官方文档，覆盖范围取决于文档是否发布

## License

MIT
