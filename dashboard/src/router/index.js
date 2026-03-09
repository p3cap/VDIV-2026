import { createRouter, createWebHistory } from "vue-router";
import MapPage from "@/views/MapPage.vue";
import DashboardPage from "@/views/DashboardPage.vue";
import AboutPage from "@/views/AboutPage.vue";
import SettingsComponent from "@/components/SettingsComponent.vue";
import { path } from "pixi.js";

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
  {
    path: "/about",
    name: "about",
    component: AboutPage,
  },
  {
    path: "/settings",
    name: "settings",
    component: SettingsComponent
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
