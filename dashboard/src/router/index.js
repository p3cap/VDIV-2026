import { createRouter, createWebHistory } from "vue-router";
import MapPage from "@/views/MapPage.vue";
import DashboardPage from "@/views/DashboardPage.vue";
import SettingsComponent from "@/components/SettingsComponent.vue";
import Map3dPage from "@/views/Map3dPage.vue";
import WelcomePage from "@/views/WelcomePage.vue";
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
    path: "/map3d",
    name: "map3d",
    component: Map3dPage,
  },
  {
    path: "/settings",
    name: "settings",
    component: SettingsComponent
  },
  {
    path: "/welcome",
    name: "welcome",
    component: WelcomePage
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
