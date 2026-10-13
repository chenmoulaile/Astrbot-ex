<template>
  <div class="rp-page">
    <v-container fluid class="pa-4 pa-md-6">
      <div class="d-flex align-center mb-3 ga-3 flex-wrap">
        <h1 class="text-h5">{{ tm("page.title") }}</h1>
        <span class="text-caption text-medium-emphasis">{{ tm("page.subtitle") }}</span>
      </div>

      <v-tabs v-model="tab" density="compact" color="primary" class="mb-4">
        <v-tab value="overview">{{ tm("tabs.overview") }}</v-tab>
        <v-tab value="cards">{{ tm("tabs.cards") }}</v-tab>
        <v-tab value="books">{{ tm("tabs.books") }}</v-tab>
        <v-tab value="import">{{ tm("tabs.import") }}</v-tab>
        <v-tab value="preview">{{ tm("tabs.preview") }}</v-tab>
      </v-tabs>

      <v-tab-panels v-model="tab">
        <v-tab-panel value="overview"><OverviewTab /></v-tab-panel>
        <v-tab-panel value="cards"><CardsTab /></v-tab-panel>
        <v-tab-panel value="books"><BooksTab /></v-tab-panel>
        <v-tab-panel value="import"><ImportTab /></v-tab-panel>
        <v-tab-panel value="preview"><PreviewTab /></v-tab-panel>
      </v-tab-panels>
    </v-container>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";

import { useModuleI18n } from "@/i18n/composables";

import BooksTab from "./rp/BooksTab.vue";
import CardsTab from "./rp/CardsTab.vue";
import ImportTab from "./rp/ImportTab.vue";
import OverviewTab from "./rp/OverviewTab.vue";
import PreviewTab from "./rp/PreviewTab.vue";

const { tm } = useModuleI18n("features/rp");
const tab = ref("overview");
</script>

<style scoped>
.rp-page {
  margin: 0 auto;
  max-width: 1280px;
}
</style>
