<script setup>
import { RouterLink} from 'vue-router';
import { Settings, Earth, ChartNoAxesCombined } from 'lucide-vue-next';
</script>
<template>
    <nav>
        <ul>
            <li id="logo"><img src="@/assets/textures/pttt_logo_mini.png" alt="logo"></li>
            <li id="map"><RouterLink to="/"><Earth /></RouterLink></li>
            <li id="dashboard"><RouterLink to="/dashboard"><ChartNoAxesCombined /></RouterLink></li>
            <!-- about -->
            <li id="settings"><RouterLink to="/"><Settings /></RouterLink></li>
        </ul>
    </nav>
</template>
<style scoped>
nav{
    position: fixed;
    left: 0;
    top: 0;
    height: 100vh;
    background-color: aliceblue;
    width: fit-content;

}

nav ul{
    display: flex;
    flex-direction: column;
    align-items: center;
    list-style-type: none;
    padding: 0;
    height: 100%;
}

#logo img{
    width: 4rem;
}

#settings{
    justify-self: end;
}

</style>