/**
 * @file perf.c
 * @brief CPU性能等级检测工具 - 专为WASM编译优化
 * 
 * 编译命令:
 *   emcc -O3 -flto -s WASM=1 -s EXPORTED_FUNCTIONS='["_classify_cpu_performance","_main"]' \
 *        -s ALLOW_MEMORY_GROWTH=1 -s ENVIRONMENT=web -o lingchat_perf.js lingchat_perf.c
 *   
 *   或者使用 GCC/G++ 本地测试:
 *   gcc -O3 -flto -march=native -o lingchat_perf lingchat_perf.c
 * 
 * 输出格式: CPU_PERF={INTERNET|LOW|MEDIUM|HIGH}\n{brand_string}
 */
#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <stdlib.h>
#include <cpuid.h>

typedef enum{
  PERF_INTERNET = 0, /**< 仅适合上网/办公 */
  PERF_LOW = 1,      /**< 低性能 */
  PERF_MEDIUM = 2,   /**< 中等性能 */
  PERF_HIGH = 3      /**< 高性能 */
} PerfTier;

/** CPU信息获取
 * @brief 获取CPU品牌字符串
 * @param brand 输出缓冲区（至少48字节）
 * @param size 缓冲区大小
 * @return 成功返回1，失败返回0
 * 
 * @note 通过CPUID 0x80000002~0x80000004叶子获取
 *       共48字节的品牌标识字符串
 */
static int get_brand_string(char *brand, size_t size){
  unsigned int eax, ebx, ecx, edx;
  unsigned int max_ext;
  // 安全检查：缓冲区必须>=48字节
  if (size < 48)
    return 0;
  // 查询扩展功能最大叶号
  if (!__get_cpuid(0x80000000, &max_ext, &ebx, &ecx, &edx))
    return 0;
  // 品牌字符串至少需要 0x80000002~0x80000004 三个叶子
  if (max_ext < 0x80000004)
    return 0;
  // 清零缓冲区
  memset(brand, 0, size);
  char *ptr = brand;
  // 依次读取三个叶子的16字节数据（合计48字节）
  for (unsigned int leaf = 0x80000002; leaf <= 0x80000004; leaf++)
  {
    if (!__get_cpuid(leaf, &eax, &ebx, &ecx, &edx))
      break;
    memcpy(ptr, &eax, 4);     ptr += 4;
    memcpy(ptr, &ebx, 4);     ptr += 4;
    memcpy(ptr, &ecx, 4);     ptr += 4;
    memcpy(ptr, &edx, 4);     ptr += 4;
  }

  // 去除前导空格（Intel品牌字符串通常有前导空格）
  char *first_non_space = brand;
  while (*first_non_space == ' ')
    first_non_space++;
  if (first_non_space != brand){
    size_t remaining = strlen(first_non_space) + 1;
    memmove(brand, first_non_space, remaining);
  }
  return 1;
}

/**
 * @brief 获取CPU Family和Model
 * @param family 输出：Family编号
 * @param model  输出：Model编号
 * 
 * @note 用于精确识别CPU微架构
 */
static void get_family_model(unsigned int *family, unsigned int *model){
  unsigned int eax, ebx, ecx, edx;
  if (!__get_cpuid(1, &eax, &ebx, &ecx, &edx)){
    *family = *model = 0;
    return;
  }
  // 解析标准Family和Model
  unsigned int base_family = (eax >> 8) & 0xF;
  unsigned int base_model  = (eax >> 4) & 0xF;
  unsigned int ext_family  = (eax >> 20) & 0xFF;
  unsigned int ext_model   = (eax >> 16) & 0xF;

  // 计算实际Family
  if (base_family == 0xF)
    *family = base_family + ext_family;
  else
    *family = base_family;

  // 计算实际Model
  if (base_family == 0x6 || base_family == 0xF)
    *model = (ext_model << 4) | base_model;
  else
    *model = base_model;
}

/* ============ 品牌字符串解析 ============ */

/**
 * @brief 从品牌字符串提取Core代数
 * @param brand CPU品牌字符串
 * @return 代数编号（如8表示第8代），失败返回-1
 * 
 * @example "Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz" -> 8
 *          "Intel(R) Core(TM) i5-12600K" -> 12
 *          "Intel(R) Core(TM) i3-10100" -> 10
 * 
 * @note Intel命名规则：型号数字除以1000取整即为代数
 *       如 i7-8550U: 8550/1000 = 8（第8代）
 *           i5-12600K: 12600/1000 = 12（第12代）
 */
static int extract_core_generation(const char *brand){
  const char *p = strstr(brand, "Core");
  if (!p)
    return -1;

  // 查找Core i系列标记（支持i3/i5/i7/i9和m3/m5/m7）
  const char *i_marker = NULL;
  const char *patterns[] = {"i3-", "i5-", "i7-", "i9-", "m3-", "m5-", "m7-"};
  
  for (int idx = 0; idx < 7; idx++){
    i_marker = strstr(p, patterns[idx]);
    if (i_marker)
      break;
  }
  if (!i_marker)
    return -1;

  // 跳过 "iX-" 或 "mX-"，指向数字起始位置
  i_marker += 3;

  // 解析连续数字串
  char *endptr;
  long model_num = strtol(i_marker, &endptr, 10);
  
  // 无有效数字
  if (endptr == i_marker)
    return -1;

  // 根据Intel命名规则推算代数
  // 型号数字>=1000时，代数 = 型号/1000（整数除法）
  // 型号数字<1000时，属于初代酷睿（如i7-920）
  if (model_num >= 1000)
    return (int)(model_num / 1000);
  else
    return -1;
}

/**
 * @brief 检查是否为低功耗CPU
 * @param brand CPU品牌字符串
 * @return 低功耗返回1，否则返回0
 * 
 * @note 低功耗后缀：U（低压移动版）、Y（极低功耗）
 *       H（标压移动版）、G（含集显低压版）、P（中等功耗）不算低压
 */
static int is_low_power_suffix(const char *brand){
    // 定位 "CPU @" 之前的型号部分
    const char *cpu_at = strstr(brand, "CPU @");
    if (!cpu_at)
      return 0;

    // 向前找到型号字符串的起始位置
    const char *end = cpu_at;
    while (end > brand && *(end - 1) != ' ')
      end--;

    // 提取型号字符串到临时缓冲区
    size_t len = cpu_at - end;
    if (len == 0 || len >= 63)
      return 0;

    char temp[64];
    memcpy(temp, end, len);
    temp[len] = '\0';

    // 检查是否包含低功耗后缀
    const char *suffix_list[] = {"U", "Y"};
    for (size_t i = 0; i < 2; i++){
      if (strstr(temp, suffix_list[i]) != NULL)
        return 1;
    }
    return 0;
}

/* ============ 核心分级逻辑 ============ */

/**
 * @brief 分类CPU性能等级
 * @return PerfTier 枚举值
 * 
 * @note 分级策略：
 *   - INTERNET: Atom、低压赛扬/奔腾、低端嵌入式
 *   - LOW: 普通赛扬/奔腾、早期i3(<5代)、低压Core(<8代)、Core 2系列
 *   - MEDIUM: 中端Core(5-7代)、Xeon E3
 *   - HIGH: 8代+Core、12代+全系、Core Ultra、Xeon E5/E7
 */
PerfTier classify_cpu_performance(void){
  // 1. 检查是否为Intel CPU
  unsigned int eax, ebx, ecx, edx;
  if (!__get_cpuid(0, &eax, &ebx, &ecx, &edx))
    return PERF_LOW;

  // "GenuineIntel"的ASCII编码（小端序）
  if (ebx != 0x756e6547 || edx != 0x49656e69 || ecx != 0x6c65746e){
    // 非Intel CPU（AMD等）暂定为LOW
    // TODO: 添加AMD Ryzen系列的分级支持
    return PERF_LOW;
  }

  // 2. 获取品牌字符串
  char brand[49] = {0};
  if (!get_brand_string(brand, sizeof(brand)))
    return PERF_LOW;

  // 3. 获取Family/Model（保留备用）
  unsigned int family, model;
  get_family_model(&family, &model);
  (void)family;  // 消除未使用变量警告
  (void)model;

  // 4. 基于品牌字符串进行分类
  // 4.1 Atom系列 -> INTERNET
  if (strstr(brand, "Atom") != NULL)
    return PERF_INTERNET;

  // 4.2 赛扬/奔腾系列
  if (strstr(brand, "Celeron") != NULL || strstr(brand, "Pentium") != NULL){
    // 低压版->INTERNET，否则->LOW
    return is_low_power_suffix(brand) ? PERF_INTERNET : PERF_LOW;
  }

  // 4.3 Core系列
  if (strstr(brand, "Core") != NULL){
    int gen = extract_core_generation(brand);
    int low_power = is_low_power_suffix(brand);
    // 8代及以上 -> HIGH
    if (gen >= 8)
      return PERF_HIGH;

    // 12代及以上特判（如i5-1240P虽为低压但性能足够）
    if (strstr(brand, "12th Gen") != NULL)
      return PERF_HIGH;

    // Core Ultra系列 -> HIGH
    if (strstr(brand, "Ultra") != NULL)
      return PERF_HIGH;
    // 1-7代Core
    if (gen > 0 && gen < 8){
      int is_i3 = (strstr(brand, "i3-") != NULL);
        // i3且代数<5 -> LOW
      if (is_i3 && gen < 5)
          return PERF_LOW;
        // 低压Core且代数<=7 -> LOW
      if (low_power && gen <= 7)
          return PERF_LOW;
        // 6代及以上i7 -> HIGH
      if (gen >= 6 && strstr(brand, "i7-") != NULL)
          return PERF_HIGH;
      // 其余桌面/标压 -> MEDIUM
      return PERF_MEDIUM;
    }
    // Core 2系列（Duo/Quad/Extreme） -> LOW
    if (strstr(brand, "Duo") != NULL || 
        strstr(brand, "Quad") != NULL || 
        strstr(brand, "Extreme") != NULL){
      return PERF_LOW;
    }
    // 未识别的低压CPU -> LOW
    if (low_power)
      return PERF_LOW;
  }

  // 4.4 Xeon系列
  if (strstr(brand, "Xeon") != NULL){
    // E5/E7多路服务器 -> HIGH
    if (strstr(brand, "E5") != NULL || strstr(brand, "E7") != NULL)
      return PERF_HIGH;
    // 其他Xeon -> MEDIUM
    return PERF_MEDIUM;
  }
  // 默认 -> LOW
  return PERF_LOW;
}

/* ============ 主函数 ============ */

/**
 * @brief 主入口
 * 
 * @note WASM环境下，此函数会被导出供JavaScript调用
 *       输出格式：CPU_PERF={等级}\nBRAND={brand_string}。
 */
int main(void){
  // 检查是否存在配置文件，存在则跳过检测
  FILE *fp = fopen("lingchat_perf.ini", "r");
  if (fp != NULL){
    fclose(fp);
    return 0;
  }
  // 获取品牌字符串
  char brand[49] = "";
  get_brand_string(brand, sizeof(brand));
  // 执行性能分级
  PerfTier tier = classify_cpu_performance();
  const char *tier_names[] = {
    "INTERNET", 
    "LOW", 
    "MEDIUM", 
    "HIGH"
  };
  printf("CPU_PERF=%s\n", tier_names[tier]);
  printf("BRAND=%s", brand);
  return 0;
}