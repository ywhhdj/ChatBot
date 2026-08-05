<script setup lang="ts">
import { qqBotChat } from '@/api/services';
import { useUserStore } from '@/stores/user';

const userStore = useUserStore()

function updateConfig(index: number, newValue: boolean | string) {
  if (userStore.serviceConfig?.qqbot.config?.[index]) {
    userStore.serviceConfig.qqbot.config[index].value = newValue
  }
}

const qqBotInfo = ref<API.QQBotInfo | null>({
  'id': '8412011246056693513',
  'username': '小白',
  'avatar': 'http://thirdqq.qlogo.cn/g?b=oidb&k=1leHrxiaL6aiasCicBQoOCcWA&kti=al5lLgwBHsE&s=0&t=1783926460',
  'share_url': 'https://qun.qq.com/qunpro/robot/qunshare?robot_uin=4010386101&robot_appid=1905169695&biz_type=0',
  'welcome_msg': ''
})
onMounted(() => {
  qqBotChat({
    callbacks: {
      onQQBotInfo: (info) => {
        qqBotInfo.value = info
      }
    }
  })
})
</script>

<template>
  <MenuItem
    size="small"
    title="连接设置"
  >
  <ServiceConfig
    v-if="userStore.serviceConfig"
    :config="userStore.serviceConfig?.qqbot.config!"
    :updateConfig="updateConfig"
  />
  <StatusMessage
    v-else
    message="未查询到机器人信息"
  />
  </MenuItem>
  <MenuItem
    size="small"
    title="机器人信息"
    buttonText="刷新"
  >
  <div v-if="qqBotInfo">
    <div class=" h-full w-full flex-col flex justify-center items-center">
      <Avatar
        class="justify-self-start flex-1"
        :name="qqBotInfo?.username"
        :src="qqBotInfo?.avatar"
      />
      <div class="flex flex-col gap-2 justify-between">
        <div class="info-item">
          <span class="font-bold">ID</span><span>{{ qqBotInfo?.id }}</span>
        </div>

        <span class="font-bold">分享链接</span>
        <div class="border border-solid border-purple-300 p-2 rounded-md">{{ qqBotInfo?.share_url }}
        </div>
        <span class="font-bold">欢迎消息</span>
        <div class="border border-solid border-purple-300 p-2 rounded-md">
          {{ qqBotInfo?.welcome_msg }}
        </div>
      </div>
    </div>

  </div>
  <StatusMessage
    v-else
    message="请先保存机器人信息"
  />
  </MenuItem>
  <MenuItem
    size="small"
    title="机器人服务"
  >
  <Button
    type="big"
    size="small"
    style="width: 30%;margin-right: 1rem;"
    @click=""
  >启用机器人</Button>
  <Button
    type="big"
    size="small"
    style="width: 30%;margin-right: 1rem;"
  >
    启动机器人
  </Button>
  <Button
    type="big"
    size="small"
    style="width: 30%;"
  >
    停止机器人
  </Button>
  </MenuItem>
</template>

<style scoped>
.font-bold {
  color: var(--accent-color);
  font-weight: bold;
  font-size: 20px;
}

.info-item {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
</style>