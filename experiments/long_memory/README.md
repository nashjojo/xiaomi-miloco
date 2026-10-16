# 长时间事件记忆：离线合成原型

**这是数据保留、故障注入及结构化历史查询实验，不是真实视频理解成绩。**
只用 Python 3.10+ 标准库、CPU，无摄像头、网络、模型权重、API Key 或 Miloco 服务依赖。

```bash
python -m unittest discover -s experiments/long_memory -v
python experiments/long_memory/evaluate.py --out /tmp/miloco-long-memory
python experiments/long_memory/evaluate.py --budget 100 --out /tmp/miloco-long-memory-budget
```

输出 `report.json`、`RESULTS.md`、分离的真值 JSON、可回放的观察 JSONL 和逐题答案/证据。
`--period` 是摘要周期秒数，`--budget` 是保留记录数（0 表示不限），不是 token 预算。
输出为合成数据，不覆盖 `knowledge/04-testing/README.md`，也不声称已有真实素材。

## 实际代码依据

检查基线提交：`03eea873eaaf94b91f3bf6ffe4eaedf6af9419ce`。

|实现|对应代码|对本实验的意义|
|---|---|---|
|Gate 双模态放行、visual hold、两者均未通过返回 None|`backend/miloco/src/miloco/perception/engine/gate/gate.py::run_gate`|故障注入只模拟某窗最终被丢弃；不实现或评测实际阈值、hold、VAD|
|Gate None 立即返回 skipped|`perception/engine/pipeline.py::run_pipeline` 及 per-device `_run_device`|本窗不会正常进入后续 Identity/Omni；不能把 skip 视为没有事件|
|按 device_id 缓存 tracker / identity engine|`perception/engine/api.py::_get_or_create_tracking_service`、`_get_or_create_identity_engine`|局部 track ID 不可直接当跨镜头身份；本实验不运行 DeepSORT|
|MeaningfulEvent API 模型|`perception/schema.py::MeaningfulEvent`|复用 event_id、timestamp、text、device_ids、has_*、snapshot_count；运行时用 AST 核对字段存在|
|分类过滤纯 caption|`perception/client.py::_persist_meaningful_event`、`perception/event_classifier.py`|全观察日志与 meaningful-only 必须分开；fixture 仅用规则标记演示过滤，不是完整 classify 重放|
|普通感知日志写入|`perception/processor.py`|raw/all_observed 是理想结构化事实日志上界；不是把 meaningful_events 当全部感知日志|
|周期摘要通过 Agent 执行|`plugins/skills/miloco-perception-digest/SKILL.md`|实际规则合并连续活动、丢弃物品清单，禁止把 unknown 追认为具名成员|
|Home Profile 是知识条目|`home_profile/schema.py::Entry`、`home_profile/render.py`、`plugins/skills/miloco-home-observe/SKILL.md`|真实模型含 evidence_log、first_seen、last_seen，但并不保证完整时序；Observe 明确丢弃一次性临时状态|

以上 Python 简写路径均相对 `backend/miloco/src/miloco/`。AST 只校验字段兼容性，不等于完整 Pydantic 运行时校验；真实集成应执行 `MeaningfulEvent.model_validate`。

**时间陷阱**：Schema 的 timestamp 注释称窗口起点，然而 `_persist_meaningful_event` 当前设置 `timestamp_ms = int(time.time() * 1000)`。原型使用固定 Unix 毫秒观测时间，是评测输入约定，不是声称修复了生产时间语义。真实接入需要同时保留 window_start/window_end、ingested_at、设备时间偏移，不用写库时间代替事件时间。

## 数据及比较设计

一分钟 10 个事件、7 道题；五小时重复相同脚本 300 次，共 3000 个事件、2100 道题。物品每分钟不同，两个真实人物，两个镜头；包含同相机离开/返回、物品转移、跨镜头携带、遮挡/再现。所有题在观察结束时提出，五小时第一组题的回溯延迟接近五小时。重复脚本用于控制局部复杂度，**不是多样化家庭行为集**。

真值不传给记忆构建器；观测侧只暴露识别结果。`facts` 是评测新增 sidecar，包含 action/object/location/person/track/camera，**并非 Omni 已经提供的结构化物体追踪结果**。用合成 caption 代替自然语言解析，相当于假设结构化抽取已完成。没有视频或片段，snapshot_count 始终为 0。

每种时长运行 6 种输入：clean、gate、identity、occlusion、cross_camera、combined。后三类分别注入返回后 unknown、隐藏一次移动、跨镜头身份未知与物体标识断裂；均为指定压力条件，不是实际错误率。每种输入分别走 all_observed 与 meaningful_only，再比较：

|记忆方式|确定性离线行为|可以回答什么|不能据此推断什么|
|---|---|---|---|
|raw|保留输入事件和事实，可选最近 N 条限制|有证据的时间/位置、动作人、返回身份、跨镜头关系|实际检索 Agent、向量搜索、VLM 或自然语言问答的正确率|
|periodic|每周期、每物品只留最后一次观察|恰好保留的末状态事实|这不是线上 digest 的 LLM 实现；结果由明确压缩策略决定|
|profile|拒收本 fixture 的一次性状态；空初始档案，无用户告知|只能对此类历史题弃答|没有运行 Observe/Promote/Prune、权重/截断；不代表真实 Profile 分数为零，也不评价偏好/习惯问答|

问题包括历史位置、搬动物品的人、离画返回身份、跨镜头人/物关联、前后位置、最后可见位置、遮挡时当前位置。检索通过 **timestamp + camera** 精确键完成，答案需要两条事实时检查二者；不接受相同局部 track ID 作为同人证据。题目定位明确，**未评价模糊时间、语义召回或自然语言检索**。证据 ID 只用于评分及引用，不传给答题器；标准答案仅评分可见。

## 评分解释

- observation_recall：进入观测日志的事件数 / 真值事件数；仅衡量注入的丢弃，不衡量 caption 语义遗漏。
- persistence_recall：写入所选日志流的事件数 / 真值事件数；与上述分开报告，避免过滤损失被摘要掩盖。
- retained_events / memory_bytes：压缩与容量效果；JSON 字节数不等于 token、向量索引或数据库开销。
- by_kind.correct/total：分任务 exact-match；身份和跨镜头题是已给定时点的关联问答，不是 IDF1/HOTA。
- evidence_correct：是否给出全部正确事件引用；accuracy、coverage、false_claim 同报，避免空答案伪装正确检索。
- 遮挡时当前位置的标准答案为 unknown；正确弃答计正确。因此空记忆也有 1/7 总准确率，**须结合 coverage 和逐任务指标**，不能只比较总分。
- lag_seconds：逐题从所需最新证据至提问的延迟，可检查数小时前问题。cpu_wall_seconds 含逐题结果写盘，不是严格 CPU profiling，也不包括推理成本。

无限容量 raw 在 clean 的两个时长应完全一致。若加预算，五小时旧事件被淘汰，一分钟仍可完整保存。这是有意设置的机制对照；不能将五小时不限容量无下降解释成长视频理解能力。真实长期实验还需变化密度、相似物体、多人物交叉、时间顺序扰动、时钟误差、长期中断等独立维度。

## 哪些信息会不可恢复

|情形|本原型验证的机制|真实系统需要补充的证据|
|---|---|---|
|Gate 跳过窗口|若唯一一次搬动只在被丢窗口，后续看到杯子不能确定谁在何时如何搬过|实际帧差/音频/hold 与视频中事件的对齐；原视频如仍保存可重跑，不能绝对称永久不可恢复|
|短暂离画|unknown 无法仅凭前后具名人物或相同编号证明是同人|真实检测/ReID、track 重建、gallery 与时间间隔；真实 DeepSORT 的时间推进不能由本脚本推断|
|遮挡|最后可见位置不是当前确定位置；隐藏动作不能从结果状态唯一还原|多视角可见性、遮挡时间、是否有人移动物体；允许 unknown，不脑补|
|跨摄像头移动|无共享人物/物体标识时，仅时间邻近不能证明跨镜头同一实体|同步视频、多目标匹配、相机拓扑、相似外观干扰及身份标注|
|摘要/Profile 丢细节|仅凭压缩产物无法回答被删事实|若原日志、evidence_log 或片段仍保留，应测试回查路径；本实验是各记忆单独可用的消融，不是完整 Agent 工具链|

下一阶段真实视频必须分别标注可见事件、遮挡/不可判定状态、人物身份、物体实例、相机与时间，并运行实际 Gate/Identity/Omni，先算感知事件匹配 precision/recall、身份连续性、物体位置与跨镜头关联，再把真实输出接到相同记忆比较层。应增加自然语言问题、拒答和引用验证，并隔离合成结果与真实视频结果。
