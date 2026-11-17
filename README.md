# bili-blacklist-exporter

> **Move a Bilibili (B站) blacklist from one account to another — export from A, import into B.**

B 站的黑名单被锁在账号里：页面只显示昵称和拉黑时间，不显示 UID，也没有导出或导入入口。换号、小号转大号、多账号同步时，只能靠人肉重新拉黑。

这个工具基于一个判断：**黑名单是一份数据，应该像通讯录一样可导出、可校验、可迁移。** 它调用 B 站 Web 端自己使用的接口，把这件事拆成两个可独立使用的阶段。

- **导出**（只读）：把账号 A 的黑名单整理成 UID 清单。
- **导入**（写入）：把 UID 清单批量拉黑到账号 B，默认空跑、显式确认、全程留痕。

---

## 迁移流程

```
账号 A ──导出──> UID 清单 ──校验──> 账号 B ──导入──> 完成
 (源)           TXT/CSV/JSON       (目标)
```

| 步骤 | 做什么 | 用的脚本 | 是否会改动账号 |
|---|---|---|---|
| 1. 导出 | 登录账号 A，拿到全部 UID | `export_blacklist.py` 或控制台脚本 | 否，只读 |
| 2. 校验 | 检查 UID 数量、格式、是否有误 | 人工看一眼 TXT / CSV | 否 |
| 3. 导入 | 登录账号 B，批量拉黑 | `import_blacklist.py` | **是**，需 `--apply` 才执行 |

整个流程不需要在两个账号间共享 Cookie：账号 A 只用来读，账号 B 只用来写，各自的登录态互不接触。

---

## 快速开始

### 第 1 步：从账号 A 导出

最省事的方式——在账号 A 的登录态下，打开 [黑名单页](https://account.bilibili.com/account/blacklist)，按 `F12` → Console，若提示 `allow pasting` 先手动输入这行并回车，然后粘贴 [`browser/export_console.js`](browser/export_console.js) 全文，浏览器会自动下载 `bilibili_blacklist.csv`。

需要机器可读的纯 UID 清单时，用命令行版：

```bash
# Cookie 获取：F12 -> Network -> 任一 bilibili.com 请求 -> Request Headers -> Cookie
python export_blacklist.py --out ./export_a --formats csv,txt
```

导出得到的 `bilibili_blacklist_uids.txt` 就是第 3 步的输入。

### 第 2 步：校验清单

打开 TXT，确认行数与账号 A 的黑名单数量一致、每行都是纯数字 UID。示例见 [`examples/sample_uids.txt`](examples/sample_uids.txt)。

### 第 3 步：导入到账号 B

把 `cookie.txt` 换成**账号 B** 的登录态（必须含 `bili_jct`），先空跑：

```bash
# 空跑：只统计和预览，不写入任何数据
python import_blacklist.py ./export_a/bilibili_blacklist_uids.txt --cookie-file cookie_B.txt

# 小批量试水：先真实拉黑 5 个，确认生效
python import_blacklist.py ./export_a/bilibili_blacklist_uids.txt \
  --cookie-file cookie_B.txt --apply --limit 5 --delay 2.0

# 全量迁移
python import_blacklist.py ./export_a/bilibili_blacklist_uids.txt \
  --cookie-file cookie_B.txt --apply --yes
```

也可以用浏览器版 [`browser/import_console.js`](browser/import_console.js)：登录账号 B，在黑名单页打开控制台，把 UID 填进脚本顶部的 `UID_TEXT`，先保持 `DO_IMPORT = false` 跑一次看预览，确认无误再改成 `true` 重新粘贴。

---

## 写操作的安全设计

导入会真实修改账号 B 的数据，因此默认按"最小意外"原则设计：

| 机制 | 行为 |
|---|---|
| **默认空跑** | 不加 `--apply` 不发任何写请求、不创建日志文件 |
| **显式确认** | `--apply` 下仍需输入 `yes`；`--yes` 仅供脚本化场景 |
| **自动去重** | 跳过账号 B 自身 UID、以及已在黑名单中的 UID，不做无效请求 |
| **限速** | 默认每次写入间隔 1.5 秒，避免触发风控 |
| **熔断** | 遇到 `-101 / -403 / -352 / 412 / 22001` 立即停止，不继续消耗批次 |
| **审计日志** | 每个 UID 的结果写入 `import_log.jsonl`（状态码、时间、批次号），便于核对与补跑 |
| **灰度入口** | `--limit N` 先跑 N 个验证效果，再全量执行 |

---

## 隐私与凭证

- **导出的 UID 清单是私人数据**：包含你拉黑过的所有账号。不要提交到公开仓库、发到群里或贴进 Issue。
- **Cookie 等于账号凭证**：不要提交 `cookie.txt` / `cookie_B.txt`，不要把 Cookie 发给任何人，不要连同截图外传。
- `.gitignore` 已排除 `cookie*.txt`、`output/`、`page*.json`、`bilibili_blacklist*.csv|txt|json`、`*_uids.txt`、`import_log*.jsonl`。
- 工具**不上传任何数据到第三方**：所有请求只发往 `api.bilibili.com`，结果只落在本机或从浏览器下载。
- 两个账号的 Cookie 从不需要同时出现在同一处：导出和导入是两个独立步骤。

---

## 运行方式与参数

两种方式覆盖不同场景：

| | 浏览器控制台 | 命令行 |
|---|---|---|
| 适合 | 一次性迁移，不想处理 Cookie | 批量、定期、脚本化 |
| 凭证 | 浏览器自动携带，无需复制 | 需要把 Cookie 存入文件 |
| 依赖 | Chrome / Edge / Brave | Python 3.8+，仅标准库 |
| 输出 | 浏览器下载 CSV | CSV / TXT / JSON + 审计日志 |

导出脚本参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--out` | `output` | 输出目录 |
| `--name` | `bilibili_blacklist` | 文件名前缀 |
| `--formats` | `csv,txt` | 可选 `csv` / `txt` / `json` |
| `--delay` | `0.25` | 每页间隔秒数 |
| `--cookie-file` | `cookie.txt` | Cookie 文件 |
| `--timeout` | `20` | 单次请求超时 |

导入脚本参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `input` | 必填 | TXT / CSV(uid 列) / JSON 路径 |
| `--apply` | 关 | 打开才会真正写入 |
| `--yes` | 关 | 跳过交互确认 |
| `--limit` | `0` | 只处理前 N 个，0 表示全部 |
| `--delay` | `1.5` | 写请求间隔秒数 |
| `--log` | `import_log.jsonl` | 审计日志路径 |
| `--cookie-file` | `cookie.txt` | 目标账号的 Cookie 文件 |

导出字段：`uid`、`uname`、`blocked_at`（本地时区）、`space_url`、`sign`。CSV 带 UTF-8 BOM，Excel 可直接打开；TXT 是纯 UID，一行一个，专供导入脚本消费。

---

## 接口说明（给二次开发者）

**导出**：

```
GET https://api.bilibili.com/x/relation/blacks?re_src=32&pn=<page>&ps=50
```

- `ps` 被服务端限制为 50，必须分页；`data.total` 是总数，最后一页通常不足 50。
- `data.list[]` 字段：`mid`、`uname`、`mtime`（Unix 秒）、`sign`、`face`、`attribute`、`tag`。
- 终止条件建议同时判断：空列表、累计去重数 >= `data.total`、页数上限。

**导入**：

```
POST https://api.bilibili.com/x/relation/modify
Content-Type: application/x-www-form-urlencoded

fid=<目标UID>&act=5&re_src=11&csrf=<bili_jct>
```

- `act=5` 拉黑，`act=6` 取消拉黑；本工具只使用 5。
- `csrf` 取自 Cookie 中的 `bili_jct`，缺失时脚本直接报错退出。
- 判断某 UID 是否已拉黑：黑名单列表中的 `attribute & 128`（位标志）。

**错误码**：`-101` Cookie 失效、`-403` CSRF 被拒、`-352` 风控、`-412` IP 被拦、`22001` 不能拉黑自己。

以上均为 B 站 **Web 端内部接口，不是公开开放 API**，随时可能调整，本项目不承诺兼容性。

---

## 常见问题

| 现象 | 处理 |
|---|---|
| 控制台提示 `allow pasting` | 手动输入 `allow pasting` 回车后再粘贴 |
| `code: -101 账号未登录` | Cookie 失效，重新登录并复制新的 |
| `code: -352` / `412` | 请求过快触发风控，加大 `--delay` 或稍后重试 |
| 导出数量与网页页数对不上 | 网页约 20 条/页，接口 50 条/页，以 `data.total` 为准 |
| 导入后数量少于清单 | 脚本已跳过自身 UID 和已拉黑 UID；查 `import_log.jsonl` |
| Excel 打开 CSV 中文乱码 | 用「数据 → 从文本/CSV」并选 UTF-8 编码 |
| 想撤销刚导入的黑名单 | 目前用网页手动取消；`act=6` 的回滚脚本见路线图 |

---

## 路线图

- [x] 导出黑名单为 CSV / TXT / JSON
- [x] 从 UID 清单批量导入（空跑默认、二次确认、限速、熔断、审计日志）
- [ ] `act=6` 取消拉黑，提供一键回滚
- [ ] 两次导出做 diff，展示新增 / 移除的 UID
- [ ] 浏览器扩展版，提供一键迁移按钮
- [ ] 迁移完成后自动生成校验报告

---

## 项目结构

```
bili-blacklist-exporter/
├── README.md                    # 本文档
├── LICENSE                      # MIT
├── .gitignore                   # 排除凭证与导出数据
├── export_blacklist.py          # 阶段 1：导出（只读）
├── import_blacklist.py          # 阶段 3：导入（写入，空跑默认）
├── browser/
│   ├── export_console.js        # 导出：控制台版
│   ├── bookmarklet.txt          # 导出：一行版书签
│   └── import_console.js        # 导入：控制台版
└── examples/
    ├── sample_output.csv        # 虚构的导出示例
    └── sample_uids.txt          # 虚构的 UID 清单示例
```

---

## License

[MIT](LICENSE)。本项目与哔哩哔哩官方无关联；写操作风险由使用者自行承担，使用前请先用 `--limit` 小批量验证。
