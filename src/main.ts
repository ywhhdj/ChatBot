import './assets/css/main.css'

import 'highlight.js/lib/common'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import { installLogForwarderPlugin } from './plugins/LogForwarder'
import pinia from './stores'

const app = createApp(App)
app.use(pinia)
app.use(router)
app.use(installLogForwarderPlugin)
app.mount('#app')
