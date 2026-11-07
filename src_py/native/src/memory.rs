//! 记忆系统的重计算内核（Rust 下沉）。
//!
//! 职责边界
//! ────────
//! 本模块不实现神经网络算子、不连数据库、不读配置文件
//! 它只接管记忆系统里"批量、纯数值、每轮都跑"的部分：
//!
//! * 向量批量 L2 归一化、批量点积/余弦打分
//! * RRF 多路融合、TF 余弦词法打分（CJK 友好）
//! * 遗忘曲线：`R(Δ,S)`、`S0`、强化增益、最终排序权重
//! * 确定性抖动（FNV-1a，与 Python 逐位一致）
//! * `EmbeddingBackend` trait：真实模型前向的接入点

use std::collections::HashMap;
use std::sync::Arc;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;

use crate::error::CoreError;

// ═══════════════════════════════════════════════════════════
// 一、业务常数（必须与 Python domain/layers.kernel_constants 一致）
// ═══════════════════════════════════════════════════════════

pub const RETENTION_NINE: f64 = 9.0;
pub const SPACING_BASE: f64 = 0.1;
pub const SPACING_RANGE: f64 = 0.9;
pub const MASSED_FACTOR: f64 = 0.2;
pub const GAIN_BASE: f64 = 1.2;
pub const IMPORTANCE_GAIN: f64 = 0.5;
pub const IMPORTANCE_S0: f64 = 3.0;
pub const SALIENCE_S0: f64 = 1.5;
pub const LAPSE_FACTOR: f64 = 0.5;
pub const LAPSE_MIN_S: f64 = 0.25;
pub const WAKE_R_FLOOR: f64 = 0.5;
pub const WAKE_GAIN_FACTOR: f64 = 0.5;
pub const JITTER_AMPLITUDE: f64 = 0.05;
pub const MASSED_WINDOW_SECONDS: f64 = 600.0;
pub const MIN_STABILITY: f64 = 0.25;
pub const RRF_K: f64 = 60.0;

/// 与 Python `LAYER_POLICY` 一一对应。
/// 顺序：working / episodic / semantic / summary / archive
const LAYER_BASE_S: [(&str, f64); 5] = [
    ("working", 1.0), ("episodic", 1.0), ("semantic", 30.0),
    ("summary", 7.0), ("archive", 7.0),
];
const LAYER_S_MAX: [(&str, f64); 5] = [
    ("working", 30.0), ("episodic", 30.0), ("semantic", 720.0),
    ("summary", 120.0), ("archive", 120.0),
];
const LAYER_RANK_FLOOR: [(&str, f64); 5] = [
    ("working", 0.2), ("episodic", 0.2), ("semantic", 0.6),
    ("summary", 0.4), ("archive", 0.0),
];

pub fn constants_map() -> HashMap<String, f64> {
    let mut out = HashMap::new();
    out.insert("massed_window_s".into(), MASSED_WINDOW_SECONDS);
    out.insert("spacing_base".into(), SPACING_BASE);
    out.insert("spacing_range".into(), SPACING_RANGE);
    out.insert("massed_factor".into(), MASSED_FACTOR);
    out.insert("gain_base".into(), GAIN_BASE);
    out.insert("importance_gain".into(), IMPORTANCE_GAIN);
    out.insert("importance_s0".into(), IMPORTANCE_S0);
    out.insert("salience_s0".into(), SALIENCE_S0);
    out.insert("retention_nine".into(), RETENTION_NINE);
    out.insert("lapse_factor".into(), LAPSE_FACTOR);
    out.insert("lapse_min_s".into(), LAPSE_MIN_S);
    out.insert("wake_r_floor".into(), WAKE_R_FLOOR);
    out.insert("wake_gain_factor".into(), WAKE_GAIN_FACTOR);
    out.insert("jitter_amplitude".into(), JITTER_AMPLITUDE);
    out.insert("usage.injected".into(), 0.3);
    out.insert("usage.referenced".into(), 0.7);
    out.insert("usage.confirmed".into(), 1.0);
    for (name, value) in LAYER_BASE_S {
        out.insert(format!("{}.base_s", name), value);
    }
    for (name, value) in LAYER_S_MAX {
        out.insert(format!("{}.s_max", name), value);
    }
    for (name, value) in LAYER_RANK_FLOOR {
        out.insert(format!("{}.rank_floor", name), value);
    }
    out
}

#[pyfunction]
pub fn memory_kernel_constants() -> HashMap<String, f64> {
    constants_map()
}

#[pyfunction]
pub fn has_memory_kernel() -> bool {
    true
}

/// 是否编译了本地 embedding 后端。
#[pyfunction]
pub fn has_embedding_backend() -> bool {
    cfg!(feature = "embedding-backend")
}

// ═══════════════════════════════════════════════════════════
// 二、纯数值辅助
// ═══════════════════════════════════════════════════════════

#[inline]
fn clamp01(v: f64) -> f64 {
    if !v.is_finite() {
        0.0
    } else {
        v.max(0.0).min(1.0)
    }
}

#[inline]
fn safe_days(v: f64) -> f64 {
    if !v.is_finite() || v < 0.0 { 0.0 } else { v }
}

/// `R(Δ, S) = 1 / (1 + Δ / (9·S))`。
#[inline]
pub fn retention(delta_days: f64, stability: f64, pinned: bool) -> f64 {
    if pinned {
        return 1.0;
    }
    let s = if stability.is_finite() {
        stability.max(MIN_STABILITY)
    } else {
        MIN_STABILITY
    };
    1.0 / (1.0 + safe_days(delta_days) / (RETENTION_NINE * s))
}

#[inline]
pub fn final_score(relevance: f64, r_eff: f64, floor: f64) -> f64 {
    let rel = if relevance.is_finite() { relevance.max(0.0) } else { 0.0 };
    let floor = clamp01(floor);
    rel * (floor + (1.0 - floor) * clamp01(r_eff))
}

/// FNV-1a 64。与 Python `domain/strength.fnv1a64` 逐位一致。
fn fnv1a64(text: &str) -> u64 {
    let mut h: u64 = 0xCBF29CE4_84222325;
    for byte in text.as_bytes() {
        h ^= *byte as u64;
        h = h.wrapping_mul(0x10000000_1B3);
    }
    h
}

pub fn jitter(memory_id: &str, day: f64) -> f64 {
    let day_i = safe_days(day).floor() as i64;
    let raw = format!("{}:{}", memory_id, day_i);
    let value = fnv1a64(&raw) as f64 / (1u64 << 63) as f64 / 2.0;
    // value ∈ [0,1) → ±5%
    (value * 2.0 - 1.0) * JITTER_AMPLITUDE
}

// ═══════════════════════════════════════════════════════════
// 三、Embedding 后端抽象
// ═══════════════════════════════════════════════════════════

/// 把文本变成向量的后端。**只定义契约，不绑定具体模型库**。
///
/// 实现必须是 `Send + Sync`：批量编码会被投递到工作线程，
/// 且 `py.allow_threads` 期间不能持有任何 Python 对象。
pub trait EmbeddingBackend: Send + Sync {
    fn dim(&self) -> usize;
    fn fingerprint(&self) -> String;
    /// 批量前向。返回行向量；长度必须与 `texts` 一致。
    fn encode_batch(&self, texts: &[String]) -> Result<Vec<Vec<f32>>, CoreError>;
}

/// 由组合根注入具体后端（Python 侧设置，或 feature 内注册）。
pub type BackendRef = Arc<dyn EmbeddingBackend>;

// ═══════════════════════════════════════════════════════════
// 四、PyMemoryKernel
// ═══════════════════════════════════════════════════════════

#[pyclass(name = "MemoryKernel")]
pub struct PyMemoryKernel {
    backend: Option<BackendRef>,
}

#[pymethods]
impl PyMemoryKernel {
    #[new]
    fn new() -> Self {
        Self { backend: None }
    }

    /// 常量表，供 Python 启动时比对。
    #[staticmethod]
    fn constants() -> HashMap<String, f64> {
        constants_map()
    }

    fn has_backend(&self) -> bool {
        self.backend.is_some()
    }

    /// 是否已编译本地推理后端（与是否有实例注册分开）。
    #[staticmethod]
    fn backend_compiled() -> bool {
        cfg!(feature = "embedding-backend")
    }

    // ── 向量 ──────────────────────────────────────────────

    /// 批量 L2 归一化。零向量保持零向量（不产生 NaN）。
    fn normalize_batch(
        &self,
        py: Python<'_>,
        vectors: Vec<Vec<f32>>,
    ) -> PyResult<Vec<Vec<f32>>> {
        if vectors.len() > 100_000 {
            return Err(PyValueError::new_err("归一化批量超过 100000 条上限"));
        }
        py.allow_threads(|| {
            Ok(vectors
                .iter()
                .map(|v| {
                    let norm = v.iter().map(|x| x * x).sum::<f32>().sqrt();
                    if norm > 0.0 && norm.is_finite() {
                        v.iter().map(|x| x / norm).collect::<Vec<f32>>()
                    } else {
                        vec![0.0f32; v.len()]
                    }
                })
                .collect())
        })
    }

    /// 查询向量与一组候选的批量内积（输入应已归一化）。
    /// 维度不符的候选返回 -inf 而不是整体失败 —— 脏数据只影响自己。
    fn dot_batch(
        &self,
        py: Python<'_>,
        query: Vec<f32>,
        matrix: Vec<Vec<f32>>,
    ) -> PyResult<Vec<f64>> {
        let q: Vec<f64> = query.iter().map(|x| *x as f64).collect();
        py.allow_threads(|| {
            Ok(matrix
                .iter()
                .map(|row| {
                    if row.len() != q.len() {
                        return f64::NEG_INFINITY;
                    }
                    row.iter().zip(q.iter()).map(|(a, b)| (*a as f64) * b).sum()
                })
                .collect())
        })
    }

    // ── 融合 ──────────────────────────────────────────────

    /// RRF。`weights` 与 `rank_lists` 一一对应；长度不足的按 1.0。
    #[pyo3(signature = (rank_lists, weights, k=60.0))]
    fn rrf_fuse(
        &self,
        py: Python<'_>,
        rank_lists: Vec<Vec<String>>,
        weights: Vec<f64>,
        k: f64,
    ) -> PyResult<Vec<(String, f64)>> {
        let k = if k.is_finite() && k >= 0.0 { k } else { RRF_K };
        py.allow_threads(move || {
            let mut scores: HashMap<String, f64> = HashMap::new();
            for (channel, ranked) in rank_lists.iter().enumerate() {
                let w = weights.get(channel).copied().unwrap_or(1.0);
                let mut seen: std::collections::HashSet<&str> =
                    std::collections::HashSet::new();
                for (rank, id) in ranked.iter().enumerate() {
                    if !seen.insert(id.as_str()) {
                        continue;
                    }
                    *scores.entry(id.clone()).or_insert(0.0) +=
                        w / (k + rank as f64 + 1.0);
                }
            }
            let mut out: Vec<(String, f64)> = scores.into_iter().collect();
            out.sort_by(|a, b| {
                b.1.partial_cmp(&a.1)
                    .unwrap_or(std::cmp::Ordering::Equal)
                    .then_with(|| a.0.cmp(&b.0))
            });
            Ok(out)
        })
    }

    /// TF 余弦词法打分。**输入须已 NFKC 归一化并小写**
    /// （Python 侧 `compute/kernel` 负责预处理；Rust 不引 unicode
    /// 归一化 crate，避免拉起额外依赖）。
    fn lexical_scores(
        &self,
        py: Python<'_>,
        query: String,
        documents: Vec<String>,
    ) -> PyResult<Vec<f64>> {
        let q = query.to_lowercase();
        py.allow_threads(move || {
            let qtf = term_freq(&cjk_ngrams(&q));
            let qnorm = norm_of(&qtf);
            Ok(documents
                .iter()
                .map(|doc| {
                    let dtf = term_freq(&cjk_ngrams(&doc.to_lowercase()));
                    let dnorm = norm_of(&dtf);
                    if qnorm <= 0.0 || dnorm <= 0.0 {
                        return 0.0;
                    }
                    let dot: f64 = qtf
                        .iter()
                        .map(|(t, v)| v * dtf.get(t).copied().unwrap_or(0.0))
                        .sum();
                    (dot / (qnorm * dnorm)).min(1.0).max(0.0)
                })
                .collect())
        })
    }

    // ── 遗忘曲线 ──────────────────────────────────────────

    /// 批量保持率。三个数组长度取最小值，缺失项按 0 / 最小稳定度处理。
    fn retention_batch(
        &self,
        py: Python<'_>,
        delta_days: Vec<f64>,
        stability: Vec<f64>,
        pinned: Vec<bool>,
    ) -> PyResult<Vec<f64>> {
        py.allow_threads(|| {
            let n = delta_days.len().min(stability.len());
            Ok((0..n)
                .map(|i| {
                    retention(
                        delta_days[i],
                        stability[i],
                        pinned.get(i).copied().unwrap_or(false),
                    )
                })
                .collect())
        })
    }

    /// `S0 = BASE_S × (1+3·imp) × (1+1.5·sal)`，受 `s_max` 限制。
    fn initial_stability_batch(
        &self,
        py: Python<'_>,
        base_s: Vec<f64>,
        s_max: Vec<f64>,
        importance: Vec<f64>,
        salience: Vec<f64>,
    ) -> PyResult<Vec<f64>> {
        py.allow_threads(|| {
            let n = base_s.len().min(s_max.len());
            Ok((0..n)
                .map(|i| {
                    let imp = clamp01(importance.get(i).copied().unwrap_or(0.0));
                    let sal = clamp01(salience.get(i).copied().unwrap_or(0.0));
                    let raw = base_s[i]
                        * (1.0 + IMPORTANCE_S0 * imp)
                        * (1.0 + SALIENCE_S0 * sal);
                    raw.min(s_max[i]).max(MIN_STABILITY)
                })
                .collect())
        })
    }

    /// 强化增益系数 `gain`（不含 S 本身）。
    fn reinforcement_gain_batch(
        &self,
        py: Python<'_>,
        r_now: Vec<f64>,
        usage_weight: Vec<f64>,
        importance: Vec<f64>,
        massed: Vec<bool>,
        wake_factor: Vec<f64>,
    ) -> PyResult<Vec<f64>> {
        py.allow_threads(|| {
            let n = r_now.len().min(usage_weight.len());
            Ok((0..n)
                .map(|i| {
                    let spacing = SPACING_BASE
                        + SPACING_RANGE * (1.0 - clamp01(r_now[i]));
                    let mass = if massed.get(i).copied().unwrap_or(false) {
                        MASSED_FACTOR
                    } else {
                        1.0
                    };
                    let wake = wake_factor.get(i).copied().unwrap_or(1.0);
                    GAIN_BASE
                        * usage_weight[i]
                        * spacing
                        * mass
                        * (1.0 + IMPORTANCE_GAIN
                            * clamp01(importance.get(i).copied().unwrap_or(0.0)))
                        * wake
                })
                .collect())
        })
    }

    /// `final = relevance × (floor + (1−floor) × R_eff)`。
    fn final_scores(
        &self,
        py: Python<'_>,
        relevance: Vec<f64>,
        r_eff: Vec<f64>,
        floors: Vec<f64>,
    ) -> PyResult<Vec<f64>> {
        py.allow_threads(|| {
            let n = relevance
                .len()
                .min(r_eff.len())
                .min(floors.len());
            Ok((0..n)
                .map(|i| final_score(relevance[i], r_eff[i], floors[i]))
                .collect())
        })
    }

    /// 确定性抖动。同一 id + 同一天恒等。
    fn jitter_batch(
        &self,
        py: Python<'_>,
        memory_ids: Vec<String>,
        day: f64,
    ) -> PyResult<Vec<f64>> {
        py.allow_threads(move || {
            Ok(memory_ids.iter().map(|id| jitter(id, day)).collect())
        })
    }

    // ── Embedding 前向 ────────────────────────────────────

    /// 批量编码。**无后端时明确报错**，绝不静默降级成 hash 向量。
    fn encode_batch(
        &self,
        py: Python<'_>,
        texts: Vec<String>,
    ) -> PyResult<Vec<Vec<f32>>> {
        let backend = self.backend.clone();
        match backend {
            Some(b) => py
                .allow_threads(move || b.encode_batch(&texts))
                .map_err(PyErr::from),
            None => Err(PyRuntimeError::new_err(
                "本地 embedding 后端未启用（feature embedding-backend 未编译或后端未注册）",
            )),
        }
    }
}

/// 由 **Rust 侧**组合根注入后端（不暴露给 Python）。
///
/// 刻意不接受 Python 回调对象：跨语言逐 batch 回调会把 GIL 重新拖回
/// 关键路径，等于抵消下沉收益；而且 Python 侧若悄悄换成另一套模型，
/// `embedding_fingerprint` 不会变，旧向量与新向量会混进同一索引
/// 后端只能在编译期确定的 Rust 实现里注册。
pub fn attach_backend(kernel: &mut PyMemoryKernel, backend: BackendRef) -> Result<(), CoreError> {
    if kernel.backend.is_some() {
        return Err(CoreError::Model("embedding 后端已注册，拒绝覆盖".into()));
    }
    kernel.backend = Some(backend);
    Ok(())
}

// ═══════════════════════════════════════════════════════════
// 五、CJK 友好分词（与 Python domain/scoring.cjk_ngrams 一致）
// ═══════════════════════════════════════════════════════════

#[inline]
fn is_cjk(c: char) -> bool {
    let u = c as u32;
    (0x3400..=0x4DBF).contains(&u)
        || (0x4E00..=0x9FFF).contains(&u)
        || (0x3040..=0x30FF).contains(&u)
        || (0xAC00..=0xD7AF).contains(&u)
}

/// 拉丁/数字词 + CJK 单字与 bigram。顺序与 Python 版无需一致
/// （TF 只依赖计数），但 token 集合必须一致。
fn cjk_ngrams(text: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();

    // 1) 拉丁/数字/下划线串
    let mut word = String::new();
    for c in text.chars() {
        if c.is_ascii_alphanumeric() || c == '_' {
            word.push(c.to_ascii_lowercase());
        } else if !word.is_empty() {
            out.push(std::mem::take(&mut word));
        }
    }
    if !word.is_empty() {
        out.push(word);
    }

    // 2) 连续 CJK 段：单字 + bigram
    let chars: Vec<char> = text.chars().collect();
    let mut i = 0usize;
    while i < chars.len() {
        if !is_cjk(chars[i]) {
            i += 1;
            continue;
        }
        let start = i;
        while i < chars.len() && is_cjk(chars[i]) {
            i += 1;
        }
        let segment = &chars[start..i];
        for c in segment {
            out.push(c.to_string());
        }
        if segment.len() >= 2 {
            for pair in segment.windows(2) {
                out.push(format!("{}{}", pair[0], pair[1]));
            }
        }
    }
    out
}

fn term_freq(tokens: &[String]) -> HashMap<String, f64> {
    let mut tf: HashMap<String, f64> = HashMap::new();
    for t in tokens {
        *tf.entry(t.clone()).or_insert(0.0) += 1.0;
    }
    tf
}

fn norm_of(tf: &HashMap<String, f64>) -> f64 {
    tf.values().map(|v| v * v).sum::<f64>().sqrt()
}
