# 山岚 · 内容订阅行为分群

将会员阅读档案转为可解释的行为群组，再制定带冻结成员清单的站内触达方案。

## 真实业务场景

模拟客户山岚内容社有会员运营组4人、编辑6人，试点240位订阅会员。原流程是运营人员导出 `山岚_会员周阅读_20261109.xlsx`，按阅读次数手工分组，再把名单和选题建议发给编辑。三个痛点是篇数与比例量纲混用、分群名单随工作簿修订漂移、内容建议无法追溯到当时的行为画像。本项目承接上游最近完整自然周的行为聚合，替代手工分组与名单归档，下游由编辑和运营负责人审阅内容主题、渠道假设及频次。

业务模块：阅读档案（录入/完整字段修订）、订阅权益（订单修订导入、批次核验、权益版本）、特征选择（2–3维、k=2–6、自然周取样）、分群图谱（标准化散点、轮廓系数、原始单位画像、群成员、纳入/排除依据）、触达方案（按发送日重算、冻结名单、站内起草、负责人签核与导出）。核心实体为Reader、SubscriptionBatch、SubscriptionEvent、EntitlementVersion、EntitlementSnapshot、Segment、Outreach；另有用户与审计记录。不连接真实会员系统或外发服务。

|角色|权限和页面|典型动作|
|---|---|---|
|admin|全部页面、审计、核验批次和独占签核|核对权益版本与可达名单后核验/签核|
|analyst|档案读写、订单修订导入、分群任务、草案与重算、导出|导入订单修订，形成群组内容草案|
|viewer|业务只读与导出，后端拒绝写操作|核对画像、冻结成员与排除依据|

## 一天的工作剧本

1. 08:50 viewer查看SL-001至SL-240的周阅读篇数、完读率、夜读占比。
2. 09:00 analyst核对输入来自同一完整自然周，修订说明保留在note。
3. 09:10 新增 `SL-241`，周阅读15篇、完读率0.8、夜读占比0.2。
4. 09:20 在订阅权益页粘贴订单修订 JSON，提交待核验批次；坏行被隔离并列出行号与原因。
5. 09:30 admin核验批次生效，生成完整权益版本；退款订单被截断，重叠订阅合并计天。
6. 09:40 在特征选择创建“11月会员阅读分群”，选择自然周（默认最近完整周）并绑定权益版本。
7. 09:50 worker执行标准化KMeans，页面展示纳入/排除会员及各自依据。
8. 10:00 起草“低频读者轻阅读试点”，填写发送日；系统按发送日与最新权益版本重算可达名单。
9. 10:10 admin签核，名单与依据冻结；10:20 viewer下载 `reader-outreach-<id>.json`，获得固定成员清单。

## 权益口径与失败态

订阅订单修订按行记录订单号、会员编号、有效起止日、退款日与修订号。同一订单只接纳修订号最大的记录，与到达顺序无关：迟到的旧修订写入明细但不再影响权益。退款只截断对应订单（退款日不再覆盖），其他订单继续有效。同一会员的重叠或相接订阅先合并区间，再按去重自然日计天，不重复计费。

每次批次核验生效都会从所有已生效批次重算一份完整权益快照并生成版本号（内容未变则复用上一版本）。分群、触达草案与签核都绑定单一完整版本，不会混用不同版本的部分数据；分群创建时冻结所选自然周（任意日期归一到周一）与纳入/排除名单，之后新版本不会让历史分群漂移。

分群取样只纳入所选自然周周一至周日 7 天都有有效权益的会员；覆盖不足、退款或从未订阅的会员记录在排除名单并给出覆盖天数与原因。触达按发送日重算：当天落在任一有效区间即可达，否则给出末次覆盖日/下次开始日。签核后名单冻结，刷新或再次签核返回 409。

批次状态为待核验→生效；坏行隔离不阻塞同批正常行，`problem_rows` 汇总坏行与已被更高修订取代的行。导入支持 `import_key` 幂等键：同一键重试取回原批次，已记账行不重复记账，中途失败后重放计数可重建；同一键行数不一致返回 409。同一订单同一修订内容不可变，内容冲突按坏行隔离。并发核验只有一次生效；并发签核只有一次成功。

样本数≤k、所选常量列、唯一特征点少于k、实际群数不足、缺失/非有限值均明确失败；不静默补值、降k或删除样本。输入验证422，重复会员编号409，队列故障503。任务失败保存failed和错误原因，修订后新建版本。worker保存成员、中心、画像、轮廓系数、scaler参数、seed和checksum。分群只描述行为相似性，不判断会员价值或因果关系。

## 快速启动

```sh
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```

前端 [localhost:18206](http://localhost:18206)，后端 [localhost:19206/docs](http://localhost:19206/docs)，PostgreSQL映射17706。演示账号 `admin@demo.local`、`analyst@demo.local`、`viewer@demo.local`，密码均 `Demo123!`。seed=3107，240会员，另建一条已生效的演示订阅批次与权益版本v1，含退款截断、重叠订阅与迟到修订样本；自然键只插入缺失账号和档案，重复执行不覆盖人工修改。`SEED_DEMO=true`时启动自动执行一次，失败记录日志但不阻塞服务。

五服务frontend/backend/worker/db/redis均有健康检查。backend等待数据库/Redis，worker还等待backend，frontend等待backend。worker真实消费Redis任务，心跳 `/tmp/heartbeat`；单worker启动恢复queued/running。数据库、Redis和产物用命名卷，产物位于共享 `/artifacts`（可用 `ARTIFACTS_DIR` 覆盖）。Nginx将 `/api/`转发到后端根路由。显式子网10.253.107.0/24规避当前机器默认地址池耗尽，可通过NETWORK_SUBNET调整。结束用 `docker compose down -v --remove-orphans` 清理本项目数据。

## 技术、目录与本地开发

|层|实现|
|---|---|
|前端|原生HTML/CSS/ES modules，Nginx1.27|
|后端|Python3.11、FastAPI、SQLAlchemy、PyJWT|
|计算|scikit-learn1.6、NumPy2.2、SciPy1.14|
|数据与队列|PostgreSQL16、Redis7|

`frontend/src/{api,stores,types,components/common,hooks,pages,router,utils,constants}` 分离网络、状态、契约、共用表格/字段/状态标签、表单工具、页面和枚举。`backend/src/{routes,controllers,services,models,schemas,middlewares,utils,constants,config}` 分离HTTP、查询、算法、持久化、校验、鉴权和配置。RequestId与SecurityHeaders为两个中间件，全局错误可恢复，业务写入有审计。ORM建初表，migrations/001_initial.sql保留实际DDL，没有在线版本迁移执行器。

本地开发先启动db/redis，在backend安装requirements，设置DATABASE_URL/REDIS_URL/JWT_SECRET后运行 `uvicorn src.main:app --reload`。前端静态文件通过Nginx同源代理，也可配置本地开发代理。环境变量见.env.example：COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、DB_PASSWORD、JWT_SECRET、SEED_DEMO、NETWORK_SUBNET、ARTIFACTS_DIR。部署时替换演示凭据与密钥。

测试：`cd backend && python -m pytest tests -q` 默认跑SQLite；设置 `TEST_DATABASE_URL=postgresql+psycopg://reader@host:port/db` 可对真实PostgreSQL运行同一套用例（含并发核验、签核竞争、导入与分群并发）。

共享枚举ROLES、STATES、FEATURES、OUTREACH_STATES在后端src/constants/enums.py和前端src/constants/enums.js；字段约束在schemas/business.py，持久化列在models/entities.py。前端共用table/fields/status，表单hooks和HTML转义utils至少两个工具。

## 范围与证据

逐条表单/API录入及完整字段修订，无CSV/Excel导入、删除、分页、在线新会员预测或自动跨版本群组对齐。订阅订单修订通过JSON数组批量提交，不支持Excel解析。触达仅站内方案与签核，不发送邮件或消息。单worker；不宣称多worker exactly-once或大规模性能；并发一致性靠唯一键、条件更新与PostgreSQL事务级 advisory lock，SQLite仅用于本地测试。Google Fonts需联网，离线使用serif/sans-serif回退。已知差异、真实测试和截图位于源码外 `../../test-artifacts/gb-3107/`。许可证MIT，见LICENSE。
