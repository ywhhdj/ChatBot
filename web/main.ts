import "./assets/css/main.css";
import { createApp } from "vue";

import App from "./App.vue";
import router from "./router";
import appMountInit from "./composables";
import pinia from "./stores";

const app = createApp(App);
app.use(pinia);
app.use(router);
app.use(appMountInit);

app.mount("#app");
