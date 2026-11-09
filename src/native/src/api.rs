//! 设备性能检测 —— `src_py/native/perf.c` 的 Rust 移植，直接对外暴露给 Python。

//! Windows 用手写 FFI，Linux 读 `/proc` `/sys`，
//! macOS 调 `sysctl`。耗时部分一律在 `py.allow_threads` 里执行，不占 GIL。

use std::cmp::Ordering as CmpOrdering;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyByteArray, PyByteArrayMethods, PyDict, PyDictMethods};

// ═══════════════════════════════════════════════════════════
// 一、数据结构（与 Python 侧 DeviceInfoData 对齐）
// ═══════════════════════════════════════════════════════════

pub const UNKNOWN_CPU: &str = "未知 CPU";
pub const UNKNOWN_GPU: &str = "未知 GPU";

#[derive(Debug, Clone)]
pub struct CpuInfo {
    pub name: String,
    pub tier: String,
    pub score: i32,
    pub cores: u32,
    pub mhz: u32,
}

#[derive(Debug, Clone)]
pub struct GpuInfo {
    pub name: String,
    pub device_id: String,
    pub tier: String,
    pub score: i32,
    /// 以字符串形式给出（与 C 版 `"0x%04X"` 一致，Pydantic 侧是 `str`）
    pub vendor_id: String,
}

#[derive(Debug, Clone)]
pub struct DeviceInfo {
    pub cpu: CpuInfo,
    pub gpu: GpuInfo,
    pub overall_tier: String,
    pub overall_score: i32,
    pub recommended_fps: i32,
    pub ram_mb: u64,
    // ── 以下为诊断扩展字段（DeviceInfoData 的 extra="ignore"，多给不报错）──
    pub platform: &'static str,
    pub bench_ops_per_sec: f64,
    pub gpu_count: usize,
}

impl DeviceInfo {
    /// 转成 Python dict（嵌套结构，可直接 `DeviceInfoData(**info)`）。
    pub fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let root = PyDict::new_bound(py);

        let cpu = PyDict::new_bound(py);
        cpu.set_item("name", self.cpu.name.as_str())?;
        cpu.set_item("tier", self.cpu.tier.as_str())?;
        cpu.set_item("score", self.cpu.score)?;
        cpu.set_item("cores", self.cpu.cores)?;
        cpu.set_item("mhz", self.cpu.mhz)?;
        root.set_item("cpu", cpu)?;

        let gpu = PyDict::new_bound(py);
        gpu.set_item("name", self.gpu.name.as_str())?;
        gpu.set_item("device_id", self.gpu.device_id.as_str())?;
        gpu.set_item("tier", self.gpu.tier.as_str())?;
        gpu.set_item("score", self.gpu.score)?;
        gpu.set_item("vendor_id", self.gpu.vendor_id.as_str())?;
        root.set_item("gpu", gpu)?;

        let overall = PyDict::new_bound(py);
        overall.set_item("tier", self.overall_tier.as_str())?;
        overall.set_item("score", self.overall_score)?;
        root.set_item("overall", overall)?;

        root.set_item("recommended_fps", self.recommended_fps)?;
        root.set_item("ram_mb", self.ram_mb)?;
        root.set_item("platform", self.platform)?;
        root.set_item("bench_ops_per_sec", self.bench_ops_per_sec)?;
        root.set_item("gpu_count", self.gpu_count)?;

        Ok(root.unbind().into_any())
    }

    /// 序列化成 JSON 字符串（字段与 C 版完全一致，转义安全）。
    pub fn to_json(&self) -> String {
        let mut s = String::with_capacity(512);
        s.push('{');
        s.push_str("\"cpu\":{");
        push_str_field(&mut s, "name", &self.cpu.name, false);
        push_str_field(&mut s, "tier", &self.cpu.tier, true);
        push_num_field(&mut s, "score", self.cpu.score as i64, true);
        push_num_field(&mut s, "cores", self.cpu.cores as i64, true);
        push_num_field(&mut s, "mhz", self.cpu.mhz as i64, true);
        s.push_str("},\"gpu\":{");
        push_str_field(&mut s, "name", &self.gpu.name, false);
        push_str_field(&mut s, "device_id", &self.gpu.device_id, true);
        push_str_field(&mut s, "tier", &self.gpu.tier, true);
        push_num_field(&mut s, "score", self.gpu.score as i64, true);
        push_str_field(&mut s, "vendor_id", &self.gpu.vendor_id, true);
        s.push_str("},\"overall\":{");
        push_str_field(&mut s, "tier", &self.overall_tier, false);
        push_num_field(&mut s, "score", self.overall_score as i64, true);
        s.push('}');
        push_num_field(&mut s, "recommended_fps", self.recommended_fps as i64, true);
        push_num_field(&mut s, "ram_mb", self.ram_mb as i64, true);
        push_str_field(&mut s, "platform", self.platform, true);
        push_num_field(&mut s, "gpu_count", self.gpu_count as i64, true);
        s.push('}');
        s
    }
}

/// JSON 字符串转义（C 版完全没有这一步，名字里有引号就会产出非法 JSON）。
fn push_escaped(out: &mut String, v: &str) {
    out.push('"');
    for c in v.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0c}' => out.push_str("\\f"),
            c if (c as u32) < 0x20 => {
                out.push_str(&format!("\\u{:04x}", c as u32));
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

fn push_str_field(out: &mut String, key: &str, value: &str, comma: bool) {
    if comma {
        out.push(',');
    }
    push_escaped(out, key);
    out.push(':');
    push_escaped(out, value);
}

fn push_num_field(out: &mut String, key: &str, value: i64, comma: bool) {
    if comma {
        out.push(',');
    }
    push_escaped(out, key);
    out.push(':');
    out.push_str(&value.to_string());
}

// ═══════════════════════════════════════════════════════════
// 二、性能数据库与分级（沿用 C 版口径，补齐常见型号）
// ═══════════════════════════════════════════════════════════

/// (匹配子串, 分数, 档位)，匹配前统一转小写。
type Db = &'static [(&'static str, i32, &'static str)];

static CPU_DB: Db = &[
    // ── 移动端 / 桌面端 Intel ──
    ("i9-14900", 100, "高性能"),
    ("i9-13900k", 98, "高性能"),
    ("i9-12900k", 96, "高性能"),
    ("i7-13700h", 88, "高性能"),
    ("i7-13620h", 84, "高性能"),
    ("i7-12700h", 82, "高性能"),
    ("i7-12700", 80, "高性能"),
    ("i5-13400", 72, "中性能"),
    ("i5-12400", 66, "中性能"),
    ("i5-1240p", 60, "中性能"),
    ("i7-1185g7", 58, "中性能"),
    ("i7-1165g7", 55, "中性能"),
    ("i5-1155g7", 52, "中性能"),
    ("i5-1135g7", 48, "中性能"),
    ("i7-1065g7", 42, "中性能"),
    ("i5-10210u", 32, "低性能"),
    ("i3-8100", 30, "低性能"),
    ("i5-8250u", 28, "低性能"),
    ("i3-7020u", 20, "低性能"),
    ("pentium", 18, "低性能"),
    ("celeron", 12, "低性能"),
    ("atom", 8, "低性能"),
    // ── AMD ──
    ("ryzen 9 7950", 95, "高性能"),
    ("ryzen 9 7900", 92, "高性能"),
    ("ryzen 7 7800", 84, "高性能"),
    ("ryzen 7 7700", 82, "高性能"),
    ("ryzen 7 5800", 78, "高性能"),
    ("ryzen 5 7600", 74, "中性能"),
    ("ryzen 5 5600", 65, "中性能"),
    ("ryzen 5 4500u", 45, "中性能"),
    ("ryzen 3", 38, "低性能"),
    // ── Apple / 其它 ──
    ("apple m3", 88, "高性能"),
    ("apple m2", 80, "高性能"),
    ("apple m1", 70, "高性能"),
    ("snapdragon", 35, "低性能"),
    ("xeon", 60, "中性能"),
];

static GPU_DB: Db = &[
    ("rtx 4090", 99, "高性能"),
    ("rx 7900", 97, "高性能"),
    ("rtx 4080", 95, "高性能"),
    ("rtx 3080", 90, "高性能"),
    ("rx 6800", 88, "高性能"),
    ("rtx 4070", 85, "高性能"),
    ("rtx 3070", 82, "高性能"),
    ("rtx 4060", 75, "高性能"),
    ("rtx 3060", 70, "高性能"),
    ("rx 7600", 70, "高性能"),
    ("rtx 4050", 62, "中性能"),
    ("apple gpu", 60, "中性能"),
    ("gtx 1660", 55, "中性能"),
    ("gtx 1650", 50, "中性能"),
    ("iris(r) xe", 50, "中性能"),
    ("iris xe", 50, "中性能"),
    ("arc(tm) a", 48, "中性能"),
    ("radeon graphics", 30, "低性能"),
    ("uhd graphics", 28, "低性能"),
    ("gtx 1050", 35, "低性能"),
    ("hd graphics", 18, "低性能"),
    // ── 兜底：只知道厂商时用厂商均值 ──
    ("nvidia", 60, "中性能"),
    ("radeon", 45, "中性能"),
];

/// 默认档位（表里没有时的兜底，与 C 版 NULL 条目一致：40 / 中性能）。
const DEFAULT_SCORE: i32 = 40;
const DEFAULT_TIER: &str = "中性能";

fn match_db(raw: &str, db: Db) -> Option<(i32, &'static str)> {
    if raw.is_empty() {
        return None;
    }
    let lower = raw.to_lowercase();
    for &(pat, score, tier) in db {
        if lower.contains(pat) {
            return Some((score, tier));
        }
    }
    None
}

fn score_to_tier(score: i32) -> &'static str {
    if score >= 75 {
        "高性能"
    } else if score >= 40 {
        "中性能"
    } else {
        "低性能"
    }
}

fn tier_to_fps(tier: &str) -> i32 {
    match tier {
        "高性能" => 60,
        "中性能" => 30,
        _ => 15,
    }
}

// ═══════════════════════════════════════════════════════════
// 三、CPU 微基准
// ═══════════════════════════════════════════════════════════

/// 基准测试串行化：并发跑基准会互相抢核，分数会偏低。
static BENCH_GATE: Mutex<()> = Mutex::new(());

/// 参考基线（ops/s）。**上线前建议在目标机型上标定一次**：
/// 取一台"中性能"参考机跑 `PyPerf().benchmark(refresh=True)`，把结果填进来。
const BENCH_BASELINE: f64 = 4_000_000.0;
/// 从基线往上（或往下）走这么多 ops/s，分数就 ±10（即 clamp 边界）。
const BENCH_SPREAD: f64 = 8_000_000.0;
/// 单轮内层循环次数（与 C 版一致，保证数值同源）
const BENCH_CHUNK: u64 = 100_000;
/// 最少测多久（与 C 版 0.05s 一致）
const BENCH_MIN_DURATION: Duration = Duration::from_millis(50);

/// 返回每秒完成的浮点运算次数（ops/s）。失败返回 0.0。
pub fn cpu_benchmark() -> f64 {
    // 中毒兜底：一次 panic 不该让后续检测全部失败
    let _gate = match BENCH_GATE.lock() {
        Ok(g) => g,
        Err(p) => p.into_inner(),
    };

    let start = Instant::now();
    let mut iters: u64 = 0;
    let mut sink = 0.0f64;
    loop {
        let mut local = 0.0f64;
        for i in 1..BENCH_CHUNK {
            let d = i as f64;
            local += d.sqrt() * d.sin() + d.cos();
        }
        // black_box：禁止编译器把整段循环优化掉（C 版用的是 volatile）
        std::hint::black_box(local);
        if local > sink {
            sink = local;
        }
        iters += 1;
        // 至少跑一轮，再由时间决定是否继续
        if start.elapsed() >= BENCH_MIN_DURATION {
            break;
        }
    }
    std::hint::black_box(sink);
    drop(_gate);

    let elapsed = start.elapsed().as_secs_f64();
    if elapsed <= 0.0 || iters == 0 {
        return 0.0;
    }
    (iters as f64 * BENCH_CHUNK as f64) / elapsed
}

/// 把基准值映射成 ±10 的修正量（C 版这里恒等于 +10）。
fn bench_adjust(bench: f64) -> i32 {
    if bench <= 0.0 {
        return 0;
    }
    let ratio = ((bench - BENCH_BASELINE) / BENCH_SPREAD).clamp(-1.0, 1.0);
    (ratio * 10.0).round() as i32
}

fn clamp_score(v: i32) -> i32 {
    v.clamp(0, 100)
}

// ═══════════════════════════════════════════════════════════
// 四、平台采集
// ═══════════════════════════════════════════════════════════

#[derive(Debug, Clone)]
pub struct RawGpu {
    pub name: String,
    pub vendor_id: u32,
    pub device_id: u32,
}

/// 逻辑核心数（跨平台）。
fn cpu_cores() -> u32 {
    std::thread::available_parallelism()
        .map(|n| n.get() as u32)
        .unwrap_or(1)
}

#[cfg(windows)]
mod sys {
    use super::RawGpu;
    use std::ffi::c_void;
    use std::ptr;

    pub const PLATFORM: &str = "windows";

    // ── 手写 FFI：不引 winapi / windows-sys，保持依赖最小化 ──

    pub const HKEY_LOCAL_MACHINE: *mut c_void = 0x8000_0002u32 as isize as *mut c_void;
    pub const RRF_RT_REG_SZ: u32 = 0x0000_0018;
    pub const RRF_RT_REG_DWORD: u32 = 0x0000_0010;
    pub const ERROR_SUCCESS: i32 = 0;

    pub const DISPLAY_DEVICE_ATTACHED_TO_DESKTOP: u32 = 0x0000_0001;
    pub const DISPLAY_DEVICE_MIRRORING_DRIVER: u32 = 0x0000_0008;

    #[link(name = "advapi32")]
    extern "system" {
        pub fn RegGetValueW(
            hkey: *mut c_void,
            sub_key: *const u16,
            value_name: *const u16,
            flags: u32,
            ty: *mut u32,
            data: *mut c_void,
            size: *mut u32,
        ) -> i32;
    }

    #[repr(C)]
    pub struct MEMORYSTATUSEX {
        pub dw_length: u32,
        pub dw_memory_load: u32,
        pub ull_total_phys: u64,
        pub ull_avail_phys: u64,
        pub ull_total_page_file: u64,
        pub ull_avail_page_file: u64,
        pub ull_total_virtual: u64,
        pub ull_avail_virtual: u64,
        pub ull_avail_extended_virtual: u64,
    }

    #[link(name = "kernel32")]
    extern "system" {
        pub fn GlobalMemoryStatusEx(ms: *mut MEMORYSTATUSEX) -> i32;
    }

    #[repr(C)]
    pub struct DISPLAY_DEVICEW {
        pub cb: u32,
        pub device_name: [u16; 32],
        pub device_string: [u16; 128],
        pub state_flags: u32,
        pub device_id: [u16; 128],
        pub device_key: [u16; 128],
    }

    #[link(name = "user32")]
    extern "system" {
        pub fn EnumDisplayDevicesW(
            device: *const u16,
            dev_num: u32,
            display_device: *mut DISPLAY_DEVICEW,
            flags: u32,
        ) -> i32;
    }

    /// `&str` → 以 NUL 结尾的 UTF-16。
    fn wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }

    /// UTF-16 定长数组 → String（按 NUL 截断，C 版 WideCharToMultiByte 缓冲不足时不补 NUL）。
    fn from_wide(buf: &[u16]) -> String {
        let end = buf.iter().position(|&c| c == 0).unwrap_or(buf.len());
        String::from_utf16_lossy(&buf[..end])
            .trim_matches(|c: char| c == '\0' || c.is_whitespace())
            .to_string()
    }

    fn reg_string(sub_key: &str, value: &str) -> Option<String> {
        let sk = wide(sub_key);
        let vk = wide(value);
        let mut buf = [0u16; 256];
        let mut size = (buf.len() * 2) as u32;
        let mut ty: u32 = 0;
        let rc = unsafe {
            RegGetValueW(
                HKEY_LOCAL_MACHINE,
                sk.as_ptr(),
                vk.as_ptr(),
                RRF_RT_REG_SZ,
                &mut ty,
                buf.as_mut_ptr() as *mut c_void,
                &mut size,
            )
        };
        if rc != ERROR_SUCCESS {
            return None;
        }
        // size 含结尾 NUL；也可能不含（RegGetValueW 保证以 NUL 结尾，但防一手）
        let units = (size as usize / 2).min(buf.len());
        let s = from_wide(&buf[..units]);
        if s.is_empty() {
            None
        } else {
            Some(s)
        }
    }

    fn reg_dword(sub_key: &str, value: &str) -> Option<u32> {
        let sk = wide(sub_key);
        let vk = wide(value);
        let mut out: u32 = 0;
        let mut size = std::mem::size_of::<u32>() as u32;
        let mut ty: u32 = 0;
        let rc = unsafe {
            RegGetValueW(
                HKEY_LOCAL_MACHINE,
                sk.as_ptr(),
                vk.as_ptr(),
                RRF_RT_REG_DWORD,
                &mut ty,
                &mut out as *mut u32 as *mut c_void,
                &mut size,
            )
        };
        if rc == ERROR_SUCCESS {
            Some(out)
        } else {
            None
        }
    }

    const CPU_KEY: &str = "HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0";

    pub fn cpu_name() -> String {
        reg_string(CPU_KEY, "ProcessorNameString").unwrap_or_else(|| super::UNKNOWN_CPU.to_string())
    }

    pub fn cpu_mhz() -> u32 {
        reg_dword(CPU_KEY, "~MHz").unwrap_or(0)
    }

    /// 枚举**所有**显示适配器（C 版只取第一个，双显卡机器会误判）。
    pub fn gpus() -> Vec<RawGpu> {
        let mut out = Vec::new();
        let mut dd: DISPLAY_DEVICEW = unsafe { std::mem::zeroed() };
        dd.cb = std::mem::size_of::<DISPLAY_DEVICEW>() as u32;

        for i in 0..16u32 {
            let ok = unsafe { EnumDisplayDevicesW(ptr::null(), i, &mut dd, 0) };
            if ok == 0 {
                break;
            }
            let attached = (dd.state_flags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP) != 0;
            let mirroring = (dd.state_flags & DISPLAY_DEVICE_MIRRORING_DRIVER) != 0;
            if !attached || mirroring {
                continue;
            }
            let name = from_wide(&dd.device_string);
            let dev_id = from_wide(&dd.device_id);
            out.push(RawGpu {
                vendor_id: parse_hex_after(&dev_id, "VEN_"),
                device_id: parse_hex_after(&dev_id, "DEV_"),
                name,
            });
        }
        out
    }

    /// 从 `PCI\VEN_10DE&DEV_2684` 里取 `VEN_`/`DEV_` 后的十六进制值。
    fn parse_hex_after(s: &str, marker: &str) -> u32 {
        match s.find(marker) {
            Some(pos) => {
                let rest = &s[pos + marker.len()..];
                let digits: String = rest.chars().take_while(|c| c.is_ascii_hexdigit()).collect();
                u32::from_str_radix(&digits, 16).unwrap_or(0)
            }
            None => 0,
        }
    }

    pub fn ram_mb() -> u64 {
        let mut ms: MEMORYSTATUSEX = unsafe { std::mem::zeroed() };
        ms.dw_length = std::mem::size_of::<MEMORYSTATUSEX>() as u32;
        let ok = unsafe { GlobalMemoryStatusEx(&mut ms) };
        if ok != 0 {
            ms.ull_total_phys / (1024 * 1024)
        } else {
            0
        }
    }

}

#[cfg(target_os = "linux")]
mod sys {
    use super::RawGpu;
    use std::fs;

    pub const PLATFORM: &str = "linux";

    fn read(path: &str) -> Option<String> {
        fs::read_to_string(path).ok()
    }

    pub fn cpu_name() -> String {
        let text = match read("/proc/cpuinfo") {
            Some(t) => t,
            None => return super::UNKNOWN_CPU.to_string(),
        };
        for line in text.lines() {
            if let Some(rest) = line.split_once(':') {
                if rest.0.trim() == "model name" || rest.0.trim() == "Hardware" {
                    let v = rest.1.trim();
                    if !v.is_empty() {
                        return v.to_string();
                    }
                }
            }
        }
        super::UNKNOWN_CPU.to_string()
    }

    pub fn cpu_mhz() -> u32 {
        // 先试 cpufreq（更准），失败再从 /proc/cpuinfo 取
        if let Some(v) = read("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq") {
            if let Ok(khz) = v.trim().parse::<u64>() {
                return (khz / 1000) as u32;
            }
        }
        if let Some(text) = read("/proc/cpuinfo") {
            for line in text.lines() {
                if let Some(rest) = line.split_once(':') {
                    if rest.0.trim() == "cpu MHz" {
                        if let Ok(m) = rest.1.trim().parse::<f64>() {
                            return m as u32;
                        }
                    }
                }
            }
        }
        0
    }

    /// Linux 没有 EnumDisplayDevices：从 DRM 设备读 vendor/device，
    /// 名字用厂商兜底（"NVIDIA (0x2684)"），够分级用。
    pub fn gpus() -> Vec<RawGpu> {
        let mut out = Vec::new();
        let Ok(entries) = fs::read_dir("/sys/class/drm") else {
            return out;
        };
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            if !name.starts_with("card") || name.contains('-') {
                continue; // 只要 card0 / card1，跳过 card0-DP-1 这类连接器
            }
            let base = entry.path().join("device");
            let vendor = read(&base.join("vendor").to_string_lossy())
                .and_then(|v| u32::from_str_radix(v.trim().trim_start_matches("0x"), 16).ok())
                .unwrap_or(0);
            let device = read(&base.join("device").to_string_lossy())
                .and_then(|v| u32::from_str_radix(v.trim().trim_start_matches("0x"), 16).ok())
                .unwrap_or(0);
            if vendor == 0 && device == 0 {
                continue;
            }
            out.push(RawGpu {
                name: format!("{} ({:#06X})", vendor_name(vendor), device),
                vendor_id: vendor,
                device_id: device,
            });
        }
        out
    }

    fn vendor_name(vendor: u32) -> &'static str {
        match vendor {
            0x10de => "NVIDIA",
            0x1002 => "AMD Radeon",
            0x8086 => "Intel",
            _ => "GPU",
        }
    }

    pub fn ram_mb() -> u64 {
        let text = match read("/proc/meminfo") {
            Some(t) => t,
            None => return 0,
        };
        for line in text.lines() {
            if let Some(rest) = line.split_once(':') {
                if rest.0.trim() == "MemTotal" {
                    // "MemTotal:       16384000 kB"
                    let kb: u64 = rest
                        .1
                        .split_whitespace()
                        .next()
                        .and_then(|v| v.parse().ok())
                        .unwrap_or(0);
                    return kb / 1024;
                }
            }
        }
        0
    }
}

#[cfg(target_os = "macos")]
mod sys {
    use super::RawGpu;
    use std::process::Command;

    pub const PLATFORM: &str = "macos";

    fn sysctl(key: &str) -> Option<String> {
        let out = Command::new("sysctl").args(["-n", key]).output().ok()?;
        if !out.status.success() {
            return None;
        }
        let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
        if s.is_empty() {
            None
        } else {
            Some(s)
        }
    }

    pub fn cpu_name() -> String {
        sysctl("machdep.cpu.brand_string")
            .or_else(|| sysctl("hw.model"))
            .unwrap_or_else(|| super::UNKNOWN_CPU.to_string())
    }

    pub fn cpu_mhz() -> u32 {
        // hw.cpufrequency 在 Apple Silicon 上不存在，返回 0 由调用方容忍
        sysctl("hw.cpufrequency")
            .and_then(|v| v.parse::<u64>().ok())
            .map(|hz| (hz / 1_000_000) as u32)
            .unwrap_or(0)
    }

    pub fn gpus() -> Vec<RawGpu> {
        // macOS 没有轻量的枚举接口（system_profiler 太重且慢，结果已缓存，可接受）
        let name = Command::new("system_profiler")
            .args(["SPDisplaysDataType"])
            .output()
            .ok()
            .and_then(|o| String::from_utf8(o.stdout).ok())
            .and_then(|t| {
                t.lines()
                    .find(|l| l.trim_start().starts_with("Chipset Model:"))
                    .map(|l| l.split_once(':').map(|x| x.1.trim().to_string()).unwrap_or_default())
            })
            .unwrap_or_else(|| "Apple GPU".to_string());

        vec![RawGpu { name, vendor_id: 0x106b, device_id: 0 }]
    }

    pub fn ram_mb() -> u64 {
        sysctl("hw.memsize")
            .and_then(|v| v.parse::<u64>().ok())
            .map(|b| b / (1024 * 1024))
            .unwrap_or(0)
    }
}

#[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
mod sys {
    use super::RawGpu;

    pub const PLATFORM: &str = "unknown";

    pub fn cpu_name() -> String {
        super::UNKNOWN_CPU.to_string()
    }
    pub fn cpu_mhz() -> u32 {
        0
    }
    pub fn gpus() -> Vec<RawGpu> {
        Vec::new()
    }
    pub fn ram_mb() -> u64 {
        0
    }
}

// ═══════════════════════════════════════════════════════════
// 五、汇总
// ═══════════════════════════════════════════════════════════

fn collect() -> DeviceInfo {
    let cpu_name = sys::cpu_name();
    let cores = cpu_cores();
    let mhz = sys::cpu_mhz();
    let ram_mb = sys::ram_mb();
    let bench = cpu_benchmark();

    // CPU：查表 + 基准微调
    let (base_score, _base_tier) = match_db(&cpu_name, CPU_DB).unwrap_or((DEFAULT_SCORE, DEFAULT_TIER));
    let cpu_score = clamp_score(base_score + bench_adjust(bench));
    let cpu_tier = score_to_tier(cpu_score).to_string();

    // GPU：枚举到的卡逐张打分，取最强的一张（C 版只取第一张，双显卡会误判）
    let gpus = sys::gpus();
    let (gpu_score, gpu_tier, gpu_name, gpu_device_id, gpu_vendor) = match gpus
        .iter()
        .map(|g| {
            let (s, t) = match_db(&g.name, GPU_DB).unwrap_or((DEFAULT_SCORE, DEFAULT_TIER));
            (s, t, g)
        })
        .max_by(|a, b| {
            let o = a.0.cmp(&b.0);
            if o == CmpOrdering::Equal {
                CmpOrdering::Greater // 同分时保持先枚举到的（主显卡优先）
            } else {
                o
            }
        }) {
        Some((s, t, g)) => (
            s,
            t.to_string(),
            if g.name.is_empty() {
                UNKNOWN_GPU.to_string()
            } else {
                g.name.clone()
            },
            format!("(0x{:08X})", g.device_id),
            format!("0x{:04X}", g.vendor_id),
        ),
        None => (
            DEFAULT_SCORE,
            DEFAULT_TIER.to_string(),
            UNKNOWN_GPU.to_string(),
            String::new(),
            "0x0000".to_string(),
        ),
    };

    let overall_score = clamp_score(cpu_score.min(gpu_score));
    let overall_tier = score_to_tier(overall_score).to_string();
    let recommended_fps = tier_to_fps(overall_tier.as_str());

    DeviceInfo {
        cpu: CpuInfo {
            name: if cpu_name.is_empty() {
                UNKNOWN_CPU.to_string()
            } else {
                cpu_name
            },
            tier: cpu_tier,
            score: cpu_score,
            cores,
            mhz,
        },
        gpu: GpuInfo {
            name: gpu_name,
            device_id: gpu_device_id,
            tier: gpu_tier,
            score: gpu_score,
            vendor_id: gpu_vendor,
        },
        overall_tier,
        overall_score,
        recommended_fps,
        ram_mb,
        platform: sys::PLATFORM,
        bench_ops_per_sec: bench,
        gpu_count: gpus.len(),
    }
}

/// 进程内缓存：默认只测一次（C 版每次调用都跑 50ms 基准）。
static CACHE: Mutex<Option<DeviceInfo>> = Mutex::new(None);

fn lock_cache() -> std::sync::MutexGuard<'static, Option<DeviceInfo>> {
    match CACHE.lock() {
        Ok(g) => g,
        Err(p) => p.into_inner(),
    }
}

/// 取设备信息。`refresh=true` 强制重测（含重新跑基准）。
pub fn detect(refresh: bool) -> DeviceInfo {
    if !refresh {
        if let Some(info) = lock_cache().clone() {
            return info;
        }
    }
    let info = collect();
    *lock_cache() = Some(info.clone());
    info
}

// ═══════════════════════════════════════════════════════════
// 六、Python 接口
// ═══════════════════════════════════════════════════════════

/// 面向对象的包装（可选用法：`core.PyPerf().info()`）。
#[pyclass]
pub struct PyPerf;

#[pymethods]
impl PyPerf {
    #[new]
    fn new() -> Self {
        PyPerf
    }

    /// 返回设备信息 dict。
    #[pyo3(signature = (refresh=false))]
    fn info(&self, py: Python<'_>, refresh: bool) -> PyResult<Py<PyAny>> {
        let info = py.allow_threads(|| detect(refresh));
        info.to_dict(py)
    }

    /// 返回设备信息 JSON 字符串（兼容老的 `json.loads` 路径）。
    #[pyo3(signature = (refresh=false))]
    fn json(&self, py: Python<'_>, refresh: bool) -> String {
        let info = py.allow_threads(|| detect(refresh));
        info.to_json()
    }

    /// 只跑 CPU 基准，返回 ops/s（用于标定 `BENCH_BASELINE`）。
    #[pyo3(signature = (refresh=false))]
    fn benchmark(&self, py: Python<'_>, refresh: bool) -> f64 {
        if refresh {
            py.allow_threads(cpu_benchmark)
        } else {
            py.allow_threads(|| detect(false).bench_ops_per_sec)
        }
    }

    /// 丢弃缓存，立即重测并返回 dict。
    fn refresh(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let info = py.allow_threads(|| detect(true));
        info.to_dict(py)
    }
}

/// `core.detect_performance(refresh=False) -> dict`
#[pyfunction]
#[pyo3(signature = (refresh=false))]
pub fn detect_performance(py: Python<'_>, refresh: bool) -> PyResult<Py<PyAny>> {
    let info = py.allow_threads(|| detect(refresh));
    info.to_dict(py)
}

/// `core.detect_performance_json(refresh=False) -> str`
#[pyfunction]
#[pyo3(signature = (refresh=false))]
pub fn detect_performance_json(py: Python<'_>, refresh: bool) -> String {
    let info = py.allow_threads(|| detect(refresh));
    info.to_json()
}

/// 兼容老的 ctypes 用法：把 JSON 写进调用方给的 `bytearray`，返回写入字节数。
#[pyfunction]
#[pyo3(signature = (buf, refresh=false))]
pub fn detect_performance_into(
    py: Python<'_>,
    buf: &Bound<'_, PyByteArray>,
    refresh: bool,
) -> PyResult<usize> {
    let json = py.allow_threads(|| detect(refresh).to_json());
    let bytes = json.as_bytes();
    if buf.len() < bytes.len() {
        return Err(PyValueError::new_err(format!(
            "缓冲区太小：需要 {} 字节，实际 {} 字节",
            bytes.len(),
            buf.len()
        )));
    }
    buf.resize(bytes.len())?;
    // SAFETY: 刚 resize 到精确长度，且此刻没有其它 Python 侧引用在写同一个 bytearray
    unsafe {
        std::ptr::copy_nonoverlapping(bytes.as_ptr(), buf.as_bytes_mut().as_mut_ptr(), bytes.len());
    }
    Ok(bytes.len())
}
