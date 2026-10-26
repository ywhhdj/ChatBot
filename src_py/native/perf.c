// perf_native.c
// MSVC:  cl /LD perf_native.c /Fe:perf_native.dll advapi32.lib user32.lib
// MinGW: gcc -shared -O2 -Wall -Wextra -o perf_native.dll perf_native.c -ladvapi32 -luser32 -lm

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>          // ← 新增：sqrt / sin / cos

// 导出宏（MinGW 和 MSVC 都支持）
#ifdef _WIN32
#  define EXPORT __declspec(dllexport)
#else
#  define EXPORT __attribute__((visibility("default")))
#endif

// ═══════════════════════════════════════════════════════════
// 一、硬件信息获取（Windows 原生）
// ═══════════════════════════════════════════════════════════

// ── CPU 名称：读注册表 ──
static void get_cpu_name(char *out, int size) {
    HKEY hKey;
    out[0] = '\0';
    if (RegOpenKeyExW(
        HKEY_LOCAL_MACHINE,
            L"HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0",
            0, KEY_READ, &hKey
        ) != ERROR_SUCCESS) {
        snprintf(out, size, "未知 CPU");
        return;
    }
    wchar_t wbuf[256] = {0};
    DWORD cbData = sizeof(wbuf);
    DWORD type = 0;
    if (RegQueryValueExW(hKey, L"ProcessorNameString", NULL, &type,
                         (LPBYTE)wbuf, &cbData) == ERROR_SUCCESS) {
        // 去首尾空格
        wchar_t *p = wbuf;
        while (*p == L' ') p++;
        wchar_t *end = p + wcslen(p);
        while (end > p && (end[-1] == L' ' || end[-1] == L'\t')) end--;
        *end = L'\0';
        WideCharToMultiByte(CP_UTF8, 0, p, -1, out, size, NULL, NULL);
    } else {
        snprintf(out, size, "未知 CPU");
    }
    RegCloseKey(hKey);
}

// ── CPU 逻辑核心数 ──
static int get_cpu_cores(void) {
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    return (int)si.dwNumberOfProcessors;
}

// ── CPU 频率（MHz，当前） ──
static int get_cpu_mhz(void) {
    HKEY hKey;
    DWORD mhz = 0, cbData = sizeof(mhz), type = 0;
    if (RegOpenKeyExW(HKEY_LOCAL_MACHINE,
            L"HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0",
            0, KEY_READ, &hKey) == ERROR_SUCCESS) {
        RegQueryValueExW(hKey, L"~MHz", NULL, &type, (LPBYTE)&mhz, &cbData);
        RegCloseKey(hKey);
    }
    return (int)mhz;
}

// ── GPU：枚举显示适配器 ──
typedef struct {
    char name[256];
    char device_id[64];
    uint32_t vendor_id;
    uint32_t hw_device_id;
} GpuInfo;

static int get_gpu(GpuInfo *out) {
    DISPLAY_DEVICEW dd;
    ZeroMemory(&dd, sizeof(dd));
    dd.cb = sizeof(dd);

    // 先清零，避免失败时返回垃圾值
    out->name[0] = '\0';
    out->device_id[0] = '\0';
    out->vendor_id = 0;
    out->hw_device_id = 0;

    for (DWORD i = 0; EnumDisplayDevicesW(NULL, i, &dd, 0); i++) {
        if (!(dd.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP)) continue;
        if (dd.StateFlags & DISPLAY_DEVICE_MIRRORING_DRIVER) continue;

        // 显示名（WCHAR → UTF-8）
        WideCharToMultiByte(CP_UTF8, 0, dd.DeviceString, -1,
                            out->name, sizeof(out->name), NULL, NULL);

        // DeviceID 是 WCHAR，要先转窄字符再解析
        char devid_a[512] = {0};
        WideCharToMultiByte(CP_UTF8, 0, dd.DeviceID, -1,
                            devid_a, sizeof(devid_a), NULL, NULL);

        const char *pven = strstr(devid_a, "VEN_");
        const char *pdev = strstr(devid_a, "DEV_");
        if (pven) out->vendor_id    = (uint32_t)strtoul(pven + 4, NULL, 16);
        if (pdev) out->hw_device_id = (uint32_t)strtoul(pdev + 4, NULL, 16);

        snprintf(out->device_id, sizeof(out->device_id),
                 "(0x%08X)", out->hw_device_id);
        return 1;
    }
    return 0;
}

// ── 物理内存（MB） ──
static int get_ram_mb(void) {
    MEMORYSTATUSEX ms;
    ms.dwLength = sizeof(ms);
    if (GlobalMemoryStatusEx(&ms)) {
        return (int)(ms.ullTotalPhys / (1024 * 1024));
    }
    return 0;
}

// ── CPU 微基准（原生，精度远高于 JS） ──
static double cpu_benchmark(void) {
     LARGE_INTEGER freq, t0, t1;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&t0);

    // 用 volatile 累加，防止编译器优化掉整个循环
    volatile double sink = 0.0;
    int iters = 0;
    do {
        for (int i = 1; i < 100000; i++) {
            double d = (double)i;
            sink += sqrt(d) * sin(d) + cos(d);
        }
        iters++;
        QueryPerformanceCounter(&t1);
    } while ((double)(t1.QuadPart - t0.QuadPart) / freq.QuadPart < 0.05);

    // 防止 sink 被误认为未使用
    if (sink == 123456789.0) return -1.0;

    double elapsed = (double)(t1.QuadPart - t0.QuadPart) / freq.QuadPart;
    return (iters * 100000.0) / (elapsed + 1e-9);
}

// ═══════════════════════════════════════════════════════════
// 二、性能数据库与分级（与 WASM 版完全一致）
// ═══════════════════════════════════════════════════════════

typedef struct {
    const char *pattern;
    int         score;
    const char *tier;
} HWEntry;

static HWEntry CPU_DB[] = {
    {"i5-1155g7",   52, "中性能"},
    {"i5-1135g7",   48, "中性能"},
    {"i7-1165g7",   55, "中性能"},
    {"i7-1185g7",   58, "中性能"},
    {"i5-1240p",    60, "中性能"},
    {"i7-12700h",   82, "高性能"},
    {"i9-13900k",   98, "高性能"},
    {"i3-8100",     30, "低性能"},
    {"i5-8250u",    28, "低性能"},
    {"celeron",     12, "低性能"},
    {"pentium",     18, "低性能"},
    {"ryzen 5 5600", 65, "中性能"},
    {"ryzen 7 5800", 78, "高性能"},
    {"ryzen 9 7950", 95, "高性能"},
    {"apple m1",     70, "高性能"},
    {"apple m2",     80, "高性能"},
    {NULL,           40, "中性能"},
};

static HWEntry GPU_DB[] = {
    {"iris(r) xe",   50, "中性能"},
    {"iris xe",      50, "中性能"},
    {"uhd graphics", 28, "低性能"},
    {"hd graphics",  18, "低性能"},
    {"rtx 4090",     99, "高性能"},
    {"rtx 4080",     95, "高性能"},
    {"rtx 3080",     90, "高性能"},
    {"rtx 3070",     82, "高性能"},
    {"rtx 3060",     70, "高性能"},
    {"gtx 1660",     55, "中性能"},
    {"gtx 1050",     35, "低性能"},
    {"rx 7900",      97, "高性能"},
    {"rx 6800",      88, "高性能"},
    {"radeon graphics", 30, "低性能"},
    {NULL,           40, "中性能"},
};

static void to_lower(const char *src, char *dst, int dst_size) {
    int i = 0;
    while (src[i] && i < dst_size - 1) {
        char c = src[i];
        dst[i] = (c >= 'A' && c <= 'Z') ? (c + 32) : c;
        i++;
    }
    dst[i] = '\0';
}

static HWEntry *match_entry(const char *raw, HWEntry *db) {
    if (!raw || !raw[0]) return NULL;
    char lower[512];
    to_lower(raw, lower, sizeof(lower));
    for (int i = 0; db[i].pattern != NULL; i++) {
        if (strstr(lower, db[i].pattern)) return &db[i];
    }
    return NULL;
}

static const char *score_to_tier(int score) {
    if (score >= 75) return "高性能";
    if (score >= 40) return "中性能";
    return "低性能";
}

static int tier_to_fps(const char *tier) {
    if (strcmp(tier, "高性能") == 0) return 60;
    if (strcmp(tier, "中性能") == 0) return 30;
    return 15;
}

// ═══════════════════════════════════════════════════════════
// 三、导出接口
// ═══════════════════════════════════════════════════════════
char *detect_performance(void) {
    char cpu_name[256];
    char gpu_name[256] = "未知 GPU";
    char gpu_device_id[64] = "";
    char gpu_tier[32];
    char cpu_tier[32];

    // CPU
    get_cpu_name(cpu_name, sizeof(cpu_name));
    int cores = get_cpu_cores();
    int mhz   = get_cpu_mhz();

    HWEntry *cpu_e = match_entry(cpu_name, CPU_DB);
    if (!cpu_e) cpu_e = &CPU_DB[sizeof(CPU_DB)/sizeof(CPU_DB[0]) - 1];
    int cpu_score = cpu_e->score;
    snprintf(cpu_tier, sizeof(cpu_tier), "%s", cpu_e->tier);

    // 用原生基准微调 ±10
    double bench = cpu_benchmark();
    if (bench > 0) {
        int adjust = (int)(bench / 200000.0);  // 归一化系数，需按实机标定
        if (adjust > 10) adjust = 10;
        if (adjust < -10) adjust = -10;
        cpu_score += adjust;
        if (cpu_score > 100) cpu_score = 100;
        if (cpu_score < 0)   cpu_score = 0;
    }

    // GPU
    GpuInfo gpu;
    if (get_gpu(&gpu)) {
        snprintf(gpu_name, sizeof(gpu_name), "%s", gpu.name);
        snprintf(gpu_device_id, sizeof(gpu_device_id), "%s", gpu.device_id);
    }else {
        // 未检测到独显/核显，保持默认值
        snprintf(gpu_name, sizeof(gpu_name), "未知 GPU");
        gpu.vendor_id = 0;
        gpu.hw_device_id = 0;
    }

    HWEntry *gpu_e = match_entry(gpu_name, GPU_DB);
    if (!gpu_e) gpu_e = &GPU_DB[sizeof(GPU_DB)/sizeof(GPU_DB[0]) - 1];
    int gpu_score = gpu_e->score;
    snprintf(gpu_tier, sizeof(gpu_tier), "%s", gpu_e->tier);

    // 综合
    int overall_score = (cpu_score < gpu_score) ? cpu_score : gpu_score;
    const char *overall_tier = score_to_tier(overall_score);
    int fps = tier_to_fps(overall_tier);

    // 组装 JSON
    char *json = (char *)malloc(1536);
    if (!json) return NULL;
    snprintf(json, 1536,
        "{"
        "\"cpu\":{\"name\":\"%s\",\"tier\":\"%s\",\"score\":%d,"
                 "\"cores\":%d,\"mhz\":%d},"
        "\"gpu\":{\"name\":\"%s\",\"device_id\":\"%s\",\"tier\":\"%s\","
                 "\"score\":%d,\"vendor_id\":\"0x%04X\"},"
        "\"overall\":{\"tier\":\"%s\",\"score\":%d},"
        "\"recommended_fps\":%d,"
        "\"ram_mb\":%d"
        "}",
        cpu_name, cpu_tier, cpu_score, cores, mhz,
        gpu_name, gpu_device_id, gpu_tier, gpu_score, gpu.vendor_id,
        overall_tier, overall_score,
        fps, get_ram_mb()
    );
    return json;
}

EXPORT int detect_performance_buf(char *buf, int size) {
    char *json = detect_performance();
    if (!json) return -1;
    int len = (int)strlen(json) + 1;
    if (len > size) { free(json); return -2; }   // 缓冲区太小
    memcpy(buf, json, len);
    free(json);
    return len;
}