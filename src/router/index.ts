import { createRouter, createWebHistory } from 'vue-router';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'main-menu',
      component: () => import('@/views/MainMemu.vue'),
    },
    {
      path: "/home",
      name: "home",
      component: () => import('@/views/HomeView.vue'),
    },
    {
      path: "/chat",
      name: "chat",
      component: () => import('@/views/ChatView.vue'),
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import('@/views/SettingsView.vue'),
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import('@/views/NotFoundView.vue'),
    },
  ],
});

export default router;
