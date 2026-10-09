# 布店经营台

单人本机使用的布店订单、利润和库存管理桌面程序。前端使用 Vue 3，后端使用 FastAPI；桌面窗口由 pywebview 承载，MySQL 保存业务数据。项目与旧程序分离：初始化时读取旧系统数据并写入新的 `app_*` 表，不修改旧业务表。

## 功能范围

- 导入拼多多、淘宝、抖音订单，支持 `.xlsx`、`.xls`、`.csv`；先预览再确认，原始 Excel 不会被修改。
- 解析订单状态、商品规格和数量；购买米数按“商品数量 × 单件规格长度”计算。无法确认长度时阻止该批次，避免默认米数造成库存/利润错误。
- 花型管理支持成本、卷长、预计到店天数和多个匹配别名；无法匹配的订单可留待处理、忽略或重新匹配。
- 订单状态变化驱动库存流水：首次导入已退款订单不回补；已有订单从非退款变为退款时回补一次。
- 库存支持按日期查看、采购整卷入库、主动出入库、盘点、采购到货记录、库存流水和补货建议。
- 生成日报、区间报告、退款明细、库存快照及出入库明细 Excel。

## 技术栈

| 层次 | 技术 | 用途 |
| --- | --- | --- |
| 桌面容器 | Python 3.11+、pywebview、WebView2（Edge Chromium） | 提供 Windows 桌面窗口及本地文件夹选择 |
| 本地 API | FastAPI、Uvicorn | 在 `127.0.0.1` 提供仅本机访问的接口 |
| 业务数据 | MySQL、SQLAlchemy、PyMySQL | 持久化商品、订单、库存事件、采购和配置相关数据 |
| 订单/报表 | pandas、openpyxl、xlrd、python-multipart | 读取平台订单文件、处理表格并输出 Excel |
| 前端 | Vue 3、Vite 6、lucide-vue-next | 桌面界面、交互组件和图标 |
| 凭据 | keyring | 通过 Windows 凭据管理器保存数据库密码 |
| 测试/打包 | pytest、httpx、PyInstaller | 后端测试和 Windows 可执行程序打包 |

具体依赖范围以 [`backend/requirements.txt`](backend/requirements.txt) 和 [`frontend/package.json`](frontend/package.json) 为准；前端锁定依赖版本的文件是 `frontend/package-lock.json`。

## 仓库结构

```text
.
├── .gitignore
├── README.md
├── backend/
│   ├── requirements.txt          # Python 运行与测试依赖
│   ├── pytest.ini                # pytest 配置
│   ├── app/
│   │   ├── main.py               # FastAPI 应用、路由注册、前端静态文件
│   │   ├── api/                  # system/settings/products/orders/inventory/reports 接口
│   │   ├── core/                 # 应用配置、数据库连接、凭据和 app_* 表初始化/兼容
│   │   ├── domain/               # 订单解析、库存和采购补货等规则
│   │   ├── services/             # 订单导入、商品、库存、报表业务流程
│   │   ├── repositories/         # 数据访问层预留包；当前尚无独立 repository 实现
│   │   └── __init__.py
│   └── tests/                    # 订单、库存、采购、报表和未匹配订单测试
├── desktop/
│   └── main.py                   # 启动本地 API、等待就绪并打开 pywebview 窗口
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.js
│   └── src/
│       ├── App.vue               # 主界面与页面/业务交互
│       ├── DatePicker.vue        # 日期选择器
│       ├── FlowerSelect.vue      # 花型搜索选择器
│       ├── VirtualTable.vue      # 大表格展示组件
│       ├── main.js               # Vue 入口
│       ├── style.css             # 全局基础样式
│       └── overrides.css         # 界面覆盖样式
└── scripts/
    ├── run_dev.ps1               # 本地构建前端并启动桌面程序
    └── build_windows.ps1         # 安装依赖并生成 Windows 桌面程序
```

当前 `repositories/` 只是预留包；数据库访问目前主要位于 `services/`，少量查询也在 API 层。新增复杂数据访问逻辑时，应考虑集中到 repository，而不是在 API 中继续堆 SQL。

### 后端职责与数据流

```text
平台订单文件 → API 预览/解析 → 用户确认 → 订单与库存流水写入 MySQL
                                      ↓
                             报表查询与 Excel 导出
```

- `api/` 将 HTTP 请求转换为业务调用和响应；接口按 `system`、`settings`、`products`、`orders`、`inventory`、`reports` 分组。
- `domain/` 放不依赖界面的订单、库存和采购规则，适合用纯单元测试验证。
- `services/` 处理跨表事务、订单导入状态变化、库存重算、采购与报表生成。
- `core/` 管理运行设置、SQLAlchemy 连接、keyring 凭据及应用表创建/字段兼容。
- 数据表使用 `app_` 前缀：`app_meta`（初始化元数据）、`app_products`（花型/成本/库存）、`app_orders`（订单行）、`app_stock_events`（库存流水）、`app_imports`（导入记录）、`app_purchase_receipts`（采购到货）、`app_ignored_unmatched`（忽略记录）、`app_flower_aliases`（花型别名）。

主要接口分组为 `/api/system`、`/api/settings`、`/api/products`、`/api/orders`、`/api/inventory` 和 `/api/reports`；启动后以 `/api/docs` 查看完整请求参数和响应结构。

## 运行环境

- Windows 10/11；运行桌面版需要 Microsoft Edge WebView2 Runtime。
- Python 3.11 或更新版本、Node.js 20 或更新版本。
- MySQL 服务需自行安装并启动；目标数据库须预先存在。程序不会安装或启动 MySQL 服务，也不会自动创建数据库。
- 安全初始化及日常运行所使用的 MySQL 账户，需要具备读取旧表、创建/更新本程序 `app_*` 表所需的权限。

## 本地开发运行

在仓库根目录打开 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_dev.ps1
```

首次运行脚本会建立 `.venv`、安装后端依赖；如前端依赖尚未安装，则安装 npm 依赖，然后构建前端并启动桌面窗口。若修改了 `backend/requirements.txt`，请在重新运行前手动更新虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

## 构建桌面程序

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

生成文件为 `release\FabricShopManager.exe`。打包后的电脑仍需要 WebView2 Runtime、可访问的 MySQL 服务和已经创建的目标数据库；不需要安装 Node.js 或单独启动浏览器。`build/`、`release/` 和前端 `dist/` 均为生成产物，不纳入 Git。

## 测试与构建验证

后端测试使用本地测试数据库/规则，不需要连接或修改 MySQL：

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m pytest tests -q
```

前端生产构建：

```powershell
Set-Location .\frontend
npm ci
npm run build
```

运行桌面程序后，可在本机打开 `http://127.0.0.1:<本次启动端口>/api/docs` 查看 API 文档。端口由桌面启动器动态选择，因此每次启动可能不同。

## 数据、配置与安全

- MySQL 配置及报表目录保存在 `%APPDATA%\FabricShopManager\settings.json`；默认数据库名为 `shop_data`，可在界面修改。数据库密码通过当前 Windows 用户的凭据管理器保存，不写入该 JSON 文件。
- 桌面运行日志保存在 `%APPDATA%\FabricShopManager\logs\desktop.log`。
- 默认报表根目录是用户文档下的 `布料店报表`；日报、区间报告、退款、库存和出入库明细使用各自的子目录，可在界面中配置。
- 本地 API 绑定 `127.0.0.1`，不面向局域网监听。
- 本程序数据写入 `app_*` 表。安全初始化只读取旧系统数据并建立新系统基线，不更新或删除旧业务表；初始化前仍应备份数据库。
- 不要把 `.env`、运行配置、数据库密码、订单原始文件、虚拟环境或构建产物提交到 Git。`.gitignore` 已排除常见本地配置和生成文件。

## 主要业务约定

- 订单统计排除未成功交易状态；规格长度按明确规则解析，订单购买米数为数量乘单件规格米数，不以缺省米数补齐无法识别的规格。
- 首次已发货导入会产生库存扣减；已存在订单后续从非退款转为退款成功时自动回补一次。首次导入即为退款状态，不扣减/回补库存，也不进入经营统计。
- 花型默认每卷 45 米；采购按整卷录入，按花型配置的卷长增加库存，采购成本引用当前每米成本。
- 智能补货建议按最近 7 天销量和花型库存/预计到店天数估算；建议仅供人工决策，不会自动下单。
- 运费采用界面设置的全局默认值（默认 ¥2.50），按系统识别的包裹标识去重，不依赖订单表中的邮费列。
