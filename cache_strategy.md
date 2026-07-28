# Cache Strategy Design

> Phase: P4.0 — 仅设计  
> 原则：缓存属于 **CoverService 外围**，不得改 Pipeline / UVR / SVC 实现  
> 命中时：跳过或缩短对应阶段，仍通过 Adapter 组装最终 `CoverResult`

---

## 1. 目标与非目标

### 目标

- 降低重复翻唱的墙钟时间（尤其 UVR ~70%+）  
- 对 Hermes/GUI 透明：仍是一次 `run`/`submit`，结果路径语义清晰  
- 可关闭：配置开关，默认建议 off 直到验证充分  

### 非目标

- 不缓存「最终艺术效果」的主观质量评估  
- 不做跨机器分布式缓存  
- 不在 Pipeline 内部插入 cache 钩子（避免污染 Legacy）

---

## 2. 缓存对象

| 层级 | 缓存什么 | 命中收益 | 优先级 |
|------|----------|----------|--------|
| **L1 UVR stems** | 人声 + 伴奏音频文件 | 跳过 audio-separator（最大） | P0 |
| **L2 SVC vocal** | 换声后的人声 wav | 跳过 so-vits-svc | P1 |
| **L3 Final mix** | 最终 cover.wav / cover.mp3 | 整段短路 | P2（谨慎） |
| 模型权重 | 磁盘已有（models/） | 已具备，非本设计重点 | — |
| ORT/Torch session | 进程内常驻 | 属 Worker，不属文件 cache | 见 worker_evolution |

推荐落地顺序：**先 L1，再 L2，L3 默认不做**（参数组合多，易错）。

### L1 内容示例

```text
cache/uvr/{content_hash}/
  vocals.flac          # 或 .wav，与现网 glob 兼容的格式
  instrumental.flac
  meta.json            # 模型名、separator 版本、创建时间
```

### L2 内容示例

```text
cache/svc/{key}/
  vocal_svc.wav
  meta.json            # model_name, pitch(f0), f0_method, speaker…
```

---

## 3. Hash / Key 策略

### 3.1 内容哈希（输入音频）

```text
audio_hash = sha256( file_bytes )   # 或 blake3
# 大文件可选：size + mtime + 采样校验；首版建议全文件 sha256
```

### 3.2 L1 UVR key

```text
uvr_key = hash_components(
  audio_hash,
  uvr_model_filename,      # e.g. UVR_MDXNET_Main.onnx
  uvr_model_file_hash,     # 可选，防权重替换
  separator_version,       # audio-separator 版本
  output_format_tag,       # flac/wav
)
```

**不含** pitch/reverb/SVC 模型（UVR 与换声无关）。

### 3.3 L2 SVC key

```text
svc_key = hash_components(
  uvr_key 或 vocals_audio_hash,  # 依赖 L1 输出内容
  svc_model_name,                # G_16000
  svc_model_file_hash,           # 可选 .pth hash
  pitch,                         # JobContext.pitch 传入 SVC 的值
  f0_method,
  speaker,
  svc_mode / config 指纹,
)
```

注意：若未来修复「pitch 双重处理」，key 必须同步变更（version 前缀）。

### 3.4 L3 Final key（若启用）

```text
final_key = hash_components(
  svc_key,
  reverb,
  mix_vocal_volume,
  mix_instrumental_volume,
  sample_rate,
  export_bitrate,
  accompaniment_hash 或 "uvr_instrumental",
)
```

### 3.5 Key 版本前缀

所有 key 带 `v1:` 前缀；策略变更时升 `v2:`，旧目录可 GC。

---

## 4. 失效规则

| 条件 | 动作 |
|------|------|
| 源音频字节变化 | audio_hash 变 → 自然未命中 |
| UVR 模型文件替换 | model hash 变 → 未命中 |
| audio-separator / so-vits 大版本升级 | `separator_version` / `svc_fingerprint` 变 |
| 用户手动清缓存 | 删 `cache/` 或按前缀删 |
| TTL（可选） | meta.json `created_at` + 配置天数；默认可不启用 TTL |
| 磁盘配额 | LRU 删除最旧 L1/L2 目录 |
| 缓存损坏（缺文件/读失败） | 视为未命中，走全量 Pipeline，打日志 |

**不**因「同一首歌不同文件名」失效——只看内容 hash。

---

## 5. 与 UVR / SVC 的关系

```text
CoverService（未来 cache 闸门）
    │
    ├─ L1 hit? ──是──► 注入 stems 路径，请求 Adapter「跳过 UVR」*
    │                   或：拷贝 stems 到 job workdir 后走现有 Pipeline
    │
    ├─ L2 hit? ──是──► 注入 SVC 人声，跳过 SVC*
    │
    └─ miss ─────────► PipelineAdapter.run（全量）
                         │
                         └─ 成功后回写 L1/L2 产物到 cache/
```

\* **Pipeline 当前无官方 skip 开关。** 设计上两种实现策略（均不改推理逻辑本体）：

| 策略 | 做法 | 侵入性 |
|------|------|--------|
| **A. 工作区预置（推荐首版）** | 命中后把 vocals/instrumental 拷入 `job_workdir/uvr/`，并扩展 Adapter/Pipeline **可选**短路——若坚持零改 Pipeline，则不可跳过执行，只能「命中后仍跑」无收益 |
| **B. 最小 Pipeline 开关（后续）** | `JobContext` 增加 `skip_uvr` / 预置路径；仅当路径存在时跳过 `uvr.separate` | 改 Pipeline 控制流，属另阶段、需单独批准 |

P4.0 **只定策略**：缓存层放 Service；**真正跳过 UVR/SVC 需要后续明确批准的 Pipeline 微改或 Adapter 级编排分叉**。  
在零改 Pipeline 阶段，仍可先实现：**缓存写入 + 命中检测指标**，跳过执行留到批准后。

### 与现网 Profiling 结论对齐

- UVR CPU 且占总时间 ~70%+ → L1 价值最高。  
- SVC 冷启动明显 → L2 对「同歌同模型重复」有价值；对「同歌换模型」无 L1 即可。  
- pitch/reverb 变化：L1 可复用，L2/L3 失效。

---

## 6. 配置草案（实现时）

```yaml
cache:
  enabled: false
  root: "cache"
  uvr_enabled: true
  svc_enabled: false
  final_enabled: false
  max_bytes: 21474836480   # 20GB
  key_version: "v1"
```

---

## 7. 安全与隐私

- 缓存目录仅本地；勿默认上传。  
- Hermes 多用户同机时：key 勿含用户名以外的隐私；路径权限收紧。  
- `meta.json` 不写完整歌词文本。

---

## 8. 非目标（本阶段）

- 不写缓存代码  
- 不改 UVR/SVC  
- 不启用 L3 为默认  
