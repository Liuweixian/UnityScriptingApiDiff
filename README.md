# Unity Scripting API Diff

比较 [Unity 官方 Scripting API 文档](https://docs.unity3d.com/ScriptReference/index.html) 在不同版本之间的 **新增、移除、变更**，并生成交互式 HTML 报告。

## 原理

工具从 Unity 文档站抓取每个版本对应的 `docdata/toc.js`（完整 API 索引树），对比两个版本之间的条目差异：

| 层级 | 数据来源 | 说明 |
|------|----------|------|
| **类型级**（类、枚举、结构体等） | `toc.js` | 快（仅 2 次请求） |
| **成员级**（方法、属性等增删） | 各类的 ScriptReference 页面 | 较慢（约 3000+ 页面） |
| **签名级**（成员签名变更） | 各成员的 ScriptReference 页面 | 最慢 |

`diff` 命令会依次完成以上三个层级的对比，并生成包含完整差异的报告。

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

### 对比两个版本

```bash
python main.py diff --from 2022.3 --to 2023.1
# → report/2022.3-to-2023.1.html
```

首次运行需要抓取大量页面，耗时较长。已下载的内容会缓存在 `tmp/`，中断后重新运行会从缓存继续。

### 同时输出 JSON

```bash
python main.py diff --from 2022.3 --to 2023.1 --json
# → report/2022.3-to-2023.1.html + report/2022.3-to-2023.1.json
```

### 自定义输出路径

```bash
python main.py diff --from 2022.3 --to 2023.1 -o my-report.html --json my-report.json
```

## 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--from` | （必填） | 旧版本，如 `2021.3` |
| `--to` | （必填） | 新版本，如 `2022.3` |
| `-o`, `--output` | `report/<from>-to-<to>.html` | HTML 报告路径 |
| `--json [PATH]` | — | 同时输出 JSON 报告 |
| `--cache-dir` | `tmp/` | 缓存目录 |
| `--no-cache` | — | 不使用本地缓存，强制重新下载 |
| `--workers` | `8` | 并发下载线程数 |
| `--request-delay` | `0.12` | 相邻请求启动的最小间隔（秒），用于避免触发限流 |
| `--max-retries` | `6` | 遇到 HTTP 429/503 时的最大重试次数 |

## 限流与重试

Unity 文档站对高频请求会返回 **HTTP 429**。工具内置了以下保护机制：

- 请求启动按 `--request-delay` 间隔排队，允许多个请求同时在途，提高吞吐
- 遇到 429/503 时按指数退避重试，并解析 `Retry-After` 响应头
- 两个版本的成员列表与签名抓取并行执行

如果仍然频繁触发限流，可以加大间隔、减少并发：

```bash
python main.py diff --from 2022.3 --to 2023.1 --workers 2 --request-delay 0.5
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

## 目录结构

| 目录 | 用途 |
|------|------|
| `tmp/` | 下载缓存等临时文件 |
| `report/` | 生成的 HTML / JSON 报告 |

报告默认命名规则：`report/<旧版本>-to-<新版本>.html`（JSON 同理）。

## 缓存

下载的数据会缓存在 `tmp/` 目录，重复运行会更快。使用 `--no-cache` 可强制重新下载。

## 限制

- 基于官方在线文档解析，需网络连接
- `toc.js` 仅包含类型级条目，不含每个方法的独立索引
- 成员签名对比依赖页面 HTML 结构，Unity 文档格式变化可能导致解析失效
- 与 [sttz/unity-api-diff](https://github.com/sttz/unity-api-diff)（反编译 DLL 对比）相比，本工具直接读官方文档，覆盖范围取决于文档是否发布

## License

MIT
