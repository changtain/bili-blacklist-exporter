# bili-blacklist-exporter

> Migrate a Bilibili (B站) blacklist between accounts: export UIDs from account A, import them into account B. Export is read-only; import is dry-run by default and requires explicit `--apply`.

B 站的黑名单页面只显示昵称和拉黑时间，不显示 UID，也没有导出/导入按钮。这个工具调用 B 站 Web 端自己使用的接口，完成两件事：

1. **导出**：把账号 A 的黑名单整理成 CSV / TXT / JSON（只读）。
2. **导入**：把 UID 列表批量拉黑到账号 B（写操作，默认 dry-run）。

典型用途是小号转大号、换账号后恢复黑名单、或把一份可信 UID 清单批量拉黑。

---

## ⚠️ 先读隐私说明

- **导出的 CSV / TXT 属于你的私人数据**：里面有你拉黑过的所有账号 UID、昵称和签名。不要把它提交到公开仓库、发到群里或贴进 Issue。
- **Cookie 等于账号凭证**：不要提交 `cookie.txt`，不要把 Cookie 发给任何人（包括本项目作者），不要写进截图。
- 本仓库根目录的 `.gitignore` 已排除 `cookie.txt`、`output/`、`page*.json`、`bilibili_blacklist*.csv|txt|json`。发布前仍建议执行一次隐私扫描（见文末）。
- 项目**不联网上传任何数据**：命令行版只请求 `api.bilibili.com`；浏览器版只在当前页面内发请求并把结果下载到本地。

---

## 两种方式

| | 浏览器控制台 | 命令行 |
|---|---|---|
| 适合 | 绝大多数用户，一次性导出 | 定期备份、脚本化、CI |
| 凭证处理 | 浏览器自动携带，**不需要复制 Cookie** | 需要手动提供 Cookie |
| 依赖 | 只需 Chrome / Edge / Brave | Python 3.8+，无第三方库 |
| 输出 | 浏览器下载 CSV | CSV / TXT / JSON |

**推荐优先用浏览器控制台方式**，它是凭证风险最低的路径。

---

## 方式 A：浏览器控制台（推荐）

1. 登录 B 站，打开 <https://account.bilibili.com/account/blacklist>
2. 按 `F12` → 切到 `Console`（控制台）
3. 若 Chrome 提示 `Don't paste code...`，先手动输入 `allow pasting` 并回车
4. 把 [`browser/export_console.js`](browser/export_console.js) 全文粘贴进去，回车
5. 浏览器自动下载 `bilibili_blacklist.csv`

脚本会逐页请求直到达到接口声明的总数，控制台会打印每页进度。全程不读取、不打印、不外传 Cookie。

> 想更省事，用 [`browser/bookmarklet.txt`](browser/bookmarklet.txt)：把里面那一行 `javascript:...` 复制成浏览器书签的网址，之后在黑名单页点一下书签即可导出，不必每次打开控制台。

---

## 方式 B：命令行

```bash
# 1. 拿到 Cookie：F12 -> Network -> 任一 bilibili.com 请求 -> Request Headers -> Cookie
#    把整条 Cookie 字符串存到同目录的 cookie.txt（该文件已被 .gitignore 排除）

# 2. 导出
python export_blacklist.py

# 自定义输出目录、格式、限速
python export_blacklist.py --out ./backup --formats csv,txt,json --delay 0.5

# 也可以用环境变量，避免 Cookie 落盘
BILI_COOKIE='SESSDATA=...; buvid3=...' python export_blacklist.py
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--cookie` | — | 直接传 Cookie 字符串（会留在 shell history，不推荐） |
| `--cookie-file` | `cookie.txt` | 读取 Cookie 的文件 |
| `--out` | `output` | 输出目录 |
| `--name` | `bilibili_blacklist` | 输出文件名前缀 |
| `--formats` | `csv,txt` | 逗号分隔，可选 `csv` / `txt` / `json` |
| `--delay` | `0.25` | 每页间隔秒数；遇到风控调到 `1.0` |
| `--timeout` | `20` | 单次请求超时秒数 |

输出示例见 [`examples/sample_output.csv`](examples/sample_output.csv)（全部为虚构数据）。

---

## 输出字段

| 列 | 含义 |
|---|---|
| `uid` | B 站用户 UID（`mid`） |
| `uname` | 昵称 |
| `blocked_at` | 拉黑时间，本地时区 `YYYY-MM-DD HH:MM:SS` |
| `space_url` | 个人空间链接 `https://space.bilibili.com/<uid>` |
| `sign` | 个性签名（换行已折叠为空格） |

CSV 带 UTF-8 BOM，Excel 双击即可正常显示中文；TXT 是纯 UID，一行一个，方便喂给其他脚本。两种方式的字段顺序与内容一致。

---

## 接口说明（给二次开发者）

```
GET https://api.bilibili.com/x/relation/blacks?re_src=32&pn=<page>&ps=50
```

- 需要登录态 Cookie（`SESSDATA` 等）。未登录返回 `code: -101`。
- `ps` 会被服务端**限制到 50**，传更大的值无效，所以必须分页。
- `data.total` 是黑名单总数；最后一页通常不足 50 条，应作为终止条件之一。
- `data.list[]` 主要字段：`mid`、`uname`、`mtime`（Unix 秒）、`sign`、`face`、`attribute`、`tag`。
- 常见错误码：`-101` 未登录 / Cookie 失效；`-352`、`412` 触发风控，需加大请求间隔。
- 这是 **Web 端内部接口，不是公开开放 API**，B 站随时可能调整。工具对此不做兼容性承诺。

分页终止条件建议同时判断：空列表、`累计去重条数 >= data.total`、以及页数上限，避免异常时死循环。

---

## 常见问题

| 现象 | 处理 |
|---|---|
| Chrome 提示 `allow pasting` | 在控制台手动输入 `allow pasting` 后回车，再粘贴 |
| `code: -101 账号未登录` | Cookie 失效或未传；重新登录并复制新的 Cookie |
| `code: -352` / `412` | 请求过快触发风控，加 `--delay 1.0` 或稍后重试 |
| Excel 打开中文乱码 | 用本工具生成的 CSV 已带 BOM；若仍乱码，用「数据 → 从文本/CSV」并选 UTF-8 |
| 导出条数与页面页数对不上 | 网页按约 20 条/页展示，接口按 50 条/页返回，以 `data.total` 为准 |
| 想要增删黑名单 | 用导入脚本 `import_blacklist.py`，见下方「导入」章节 |

---

## 迁移：把账号 A 的黑名单搬到账号 B

### 第 1 步：从账号 A 导出

用上面的导出脚本（控制台或 CLI），得到 `bilibili_blacklist.csv` 或纯 UID 的 `.txt`。建议用 CLI 以便后续脚本读取：

```bash
python export_blacklist.py --out ./export_a --formats csv,txt
```

### 第 2 步：导入到账号 B

**先 dry-run**，确认数量和 UID 无误后再 `--apply`：

```bash
# 把 cookie.txt 换成账号 B 的登录态（含 bili_jct）
python import_blacklist.py ./export_a/bilibili_blacklist_uids.txt --cookie-file cookie_B.txt

# 确认输出无误后，加 --apply 真正写入；首次建议先小批量试水
python import_blacklist.py ./export_a/bilibili_blacklist_uids.txt \
  --cookie-file cookie_B.txt --apply --limit 5 --delay 2.0

# 全量执行
python import_blacklist.py ./export_a/bilibili_blacklist_uids.txt \
  --cookie-file cookie_B.txt --apply --yes
```

脚本的安全设计：

- **默认 dry-run**，不加 `--apply` 不会写入任何数据
- `--apply` 下仍需交互输入 `yes` 确认（或用 `--yes` 跳过，用于脚本化）
- 自动跳过**目标账号自身的 UID** 和**已在黑名单中的 UID**，不做重复请求
- 每批写操作默认间隔 `1.5s`，可通过 `--delay` 调整；遇到风控码 `-352` / `412` 会**立即停止**
- 每个 UID 的结果写入 `import_log.jsonl`（含状态码、时间、批次号），便于审计与补跑

### 导入接口说明

```
POST https://api.bilibili.com/x/relation/modify
Content-Type: application/x-www-form-urlencoded

fid=<目标UID>&act=5&re_src=11&csrf=<bili_jct>
```

- `act=5` 拉黑，`act=6` 取消拉黑（本工具只用 5）
- `csrf` 来自 Cookie 中的 `bili_jct`，缺失时脚本直接报错
- 判断某 UID 是否已拉黑：拉黑列表中该用户的 `attribute & 128`（位标志）
- 常见错误码：`-101` Cookie 失效、`-403` CSRF 被拒、`-352` 风控、`-412` IP 被拦、`22001` 不能拉黑自己

### 浏览器版导入

[`browser/import_console.js`](browser/import_console.js) 提供同样能力的控制台版本：登录**目标账号**，在黑名单页打开控制台，把 UID 填进脚本顶部的 `UID_TEXT`，并将 `DO_IMPORT` 改为 `true` 后粘贴运行。**同样需要先 dry-run 一次确认清单。**

---

## 范围与路线图

- [x] 导出黑名单为 CSV / TXT / JSON
- [x] 从 UID 列表批量导入（dry-run 默认、二次确认、限速、审计日志）
- [ ] 取消拉黑（`act=6`），用于回滚
- [ ] 两次导出做 diff，展示新增 / 移除的 UID
- [ ] 浏览器扩展版，提供一键按钮
- [ ] 支持导出为 Markdown 表格

---

## 项目结构

```
bili-blacklist-exporter/
├── README.md                    # 本文档
├── LICENSE                      # MIT
├── .gitignore                   # 排除凭证与导出数据
├── export_blacklist.py          # 命令行导出器（仅标准库，只读）
├── import_blacklist.py          # 命令行导入器（写操作，dry-run 默认）
├── browser/
│   ├── export_console.js        # 导出：控制台脚本（零凭证操作）
│   ├── bookmarklet.txt          # 导出：一行版，可存为书签
│   └── import_console.js        # 导入：控制台脚本（需显式开启写入）
└── examples/
    └── sample_output.csv         # 虚构数据示例
```

---

## 发布到 GitHub（本地操作）

本机 `git` 可用，`gh` CLI 未安装，所以使用手写 remote 的方式：

```bash
cd bili-blacklist-exporter

git init          # 若目录已初始化过，可跳过这一步
git add .
git commit -m "Initial release: Bilibili blacklist exporter"

# 先在 GitHub 网页新建一个**空**仓库（不要勾选 Add README / .gitignore / License）
git remote add origin https://github.com/<YOUR_NAME>/bili-blacklist-exporter.git
git branch -M main
git push -u origin main
```

**推送前做一次隐私扫描**，确认没有任何真实 UID、昵称或 Cookie 被带进去：

```bash
# 列出即将提交的文件，人工确认没有 cookie.txt / output/ / page*.json
git status --short
git ls-files

# 搜索可能的凭证关键字（应无输出）
git grep -n -E 'SESSDATA|bili_jct|DedeUserID' -- . ':!README.md' || echo "clean"
```

建议的仓库描述：

> Export your Bilibili blocked-user list (UIDs, nicknames, timestamps) to CSV/TXT/JSON. Privacy-first, read-only, standard library only.

建议 topics：`bilibili` `blacklist` `export` `csv` `privacy` `python` `userscript`

---

## License

[MIT](LICENSE). 本项目与哔哩哔哩官方无关联；使用风险由使用者自行承担。
