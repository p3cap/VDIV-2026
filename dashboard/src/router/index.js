import { createRouter, createWebHistory } from "vue-router";
import Map2dPage from "@/views/Map2dPage.vue";
import DashboardPage from "@/views/DashboardPage.vue";
import Map3dPage from "@/views/Map3dPage.vue";
import DocumentationPage from "@/views/DocumentationPage.vue";
import WelcomePage from "@/views/WelcomePage.vue";

const routes = [
  {
    path: "/",
    name: "welcome",
    component: WelcomePage
  },
  {
    path: "/map",
    name: "map",
    component: Map2dPage,
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
    path : "/documentation",
    name: "documentation",
    component: DocumentationPage
  }


];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
