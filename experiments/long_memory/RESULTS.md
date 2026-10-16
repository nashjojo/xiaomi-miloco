# 合成机制实验结果

不是视频/VLM 成绩。8 个 unittest 通过；两套配置各执行 72 组比较。原始逐题输出由 README 命令重建。

|Budget|Seconds|Fault|Memory|Retained|Exact match|Coverage|
|---|---|---|---|---|---|---|
|unlimited|60|clean|raw|10|1.0000|1.0000|
|unlimited|60|clean|periodic|1|0.2857|0.1667|
|unlimited|60|clean|profile|0|0.1429|0.0000|
|unlimited|60|combined|raw|8|0.2857|0.1667|
|unlimited|60|combined|periodic|2|0.2857|0.1667|
|unlimited|60|combined|profile|0|0.1429|0.0000|
|unlimited|18000|clean|raw|3000|1.0000|1.0000|
|unlimited|18000|clean|periodic|300|0.2857|0.1667|
|unlimited|18000|clean|profile|0|0.1429|0.0000|
|unlimited|18000|combined|raw|2400|0.2857|0.1667|
|unlimited|18000|combined|periodic|600|0.2857|0.1667|
|unlimited|18000|combined|profile|0|0.1429|0.0000|
|100 records|60|clean|raw|10|1.0000|1.0000|
|100 records|60|clean|periodic|1|0.2857|0.1667|
|100 records|60|clean|profile|0|0.1429|0.0000|
|100 records|60|combined|raw|8|0.2857|0.1667|
|100 records|60|combined|periodic|2|0.2857|0.1667|
|100 records|60|combined|profile|0|0.1429|0.0000|
|100 records|18000|clean|raw|100|0.1714|0.0333|
|100 records|18000|clean|periodic|100|0.1905|0.0556|
|100 records|18000|clean|profile|0|0.1429|0.0000|
|100 records|18000|combined|raw|100|0.1490|0.0072|
|100 records|18000|combined|periodic|100|0.1667|0.0278|
|100 records|18000|combined|profile|0|0.1429|0.0000|

无限预算 clean/raw 两个时长均为 1.0，是预设完美结构化观测下的保存/查询上界。Profile 对临时事件全部弃答：总分 1/7 来自遮挡问题的正确弃答，coverage 为 0。请同时看分任务结果，勿把总分当感知成绩。
