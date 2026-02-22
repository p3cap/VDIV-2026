import { createRouter, createWebHistory } from "vue-router";
import MapPage from "@/views/MapPage.vue";
import DashboardPage from "@/views/DashboardPage.vue";

const routes = [
  {
    path: "/",
    name: "map",
    component: MapPage,
  },
  {
    path: "/dashboard",
    name: "dashboard",
    component: DashboardPage,
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
