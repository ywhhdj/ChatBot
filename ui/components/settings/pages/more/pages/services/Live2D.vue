<script lang="ts" setup>

import { registerDownloadHandler } from '@/api/websocket/handlers/download';
import { useUserStore } from '@/stores/user';

const userStore = useUserStore()
const modelFolder = ref('');

function updateConfig(index: number, newValue: boolean | string) {
  if (userStore.serviceConfig?.live2d?.fields?.[index]) {
    userStore.serviceConfig.live2d.fields[index].default = newValue
  }
}

const faceOfficialDownload = () => {
  window.open('https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task')
}
const faceClicklocalDownload = () => {
  registerDownloadHandler({
    model_name: 'google_facelandmarker',
    save_path: modelFolder.value,
    callbacks: {
      onRunning: (data) => {
        console.log('下载进度:', data.progress)
      },
      onCompleted: () => {
        console.log('下载完成')
      },
      onError: (error) => {
        console.error('下载失败:', error)
      }
    }
  })
}
</script>

<template>
  <MenuItem
    size="small"
    title="Live2D模型设置"
  >
  <ServiceConfig
    service="live2d"
    :updateConfig="updateConfig"
  />
  </MenuItem>
  <MenuItem
    size="small"
    title="Live2D服务"
  >
  <Button
    type="big"
    size="small"
    style="width: 30%;margin-right: 1rem;"
    @click=""
  >启用Live2D服务</Button>
  <Button
    type="big"
    size="small"
    style="width: 30%;margin-right: 1rem;"
  >
    启动Live2D服务
  </Button>
  <Button
    type="big"
    size="small"
    style="width: 30%;"
  >
    停止Live2D服务
  </Button>
  </MenuItem>
  <MenuItem
    size="small"
    title="轻量人脸识别模型下载"
  >
  <Button
    type="big"
    size="small"
    style="width: 48%;margin-right: 1rem;"
    @click="faceOfficialDownload"
  >官网下载</Button>
  <Button
    type="big"
    size="small"
    style="width:48%;"
    @click="faceClicklocalDownload"
  >
    点击下载
  </Button>
  </MenuItem>
</template>
