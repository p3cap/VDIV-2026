import { createRouter, createWebHistory } from "vue-router";
import MapTestPage from "@/views/MapTestPage.vue";

const routes = [
  {
    path: "/",
    name: "map",
    component: MapTestPage,
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
