<template>
  <div class="service-list">
    <ServiceCard
      v-for="service in services"
      :key="service.id"
      class="service-item"
    >
      <!-- 顶部：名称 + 描述 + 状态指示灯 -->
      <div
        class="service-header"
        @click="toggleExpand(service.id)"
      >
        <div class="header-left">
          <h3 class="service-name">{{ service.name }}</h3>
          <p class="service-desc">{{ service.description }}</p>
        </div>
        <div class="header-right">
          <span
            class="status-indicator"
            :style="{
              backgroundColor: statusColor(service.status)
            }"
          ></span>
          <span class="status-text">{{ statusLabel(service.status) }}</span>
          <span class="expand-icon">{{ isExpanded(service.id) ? '▾' : '▸' }}</span>
        </div>
      </div>
      <!-- 底部配置区（展开时显示） -->
      <div
        v-show="isExpanded(service.id)"
        class="service-config"
      >
        <RowItem
          v-for="(configItem, index) in service.config"
          :key="index"
          class="config-row"
        >
          <!-- 左侧：标签 + 描述 -->
          <template #left>
            <div class="config-label">
              <span class="config-title">{{ configItem.label }}</span>
              <span
                v-if="configItem.description"
                class="config-desc"
              >{{ configItem.description }}</span>
            </div>
          </template>

          <!-- 右侧：根据类型渲染控件 -->
          <template
            #right
            class="config-control"
          >
            <Checkbox
              v-if="configItem.type === 'boolean'"
              :checked="configItem.value as boolean"
              @checked="(val: boolean) => updateConfig(service.id, index, val)"
            />
            <Select
              :options="configItem.options!"
              v-else-if="configItem.type === 'select'"
              :value="configItem.value as string"
              @change="(val: string) => updateConfig(service.id, index, val)"
            />
            <Input
              v-else-if="configItem.type === 'string'"
              class="config-input"
              :value="configItem.value as string"
              @input="(val: string | boolean) => updateConfig(service.id, index, val)"
            />
          </template>
        </RowItem>
      </div>
    </ServiceCard>
  </div>
</template>