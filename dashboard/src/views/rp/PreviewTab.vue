<template>
  <div>
    <v-card variant="outlined" class="pa-4 mb-4">
      <v-row dense>
        <v-col cols="12" md="5">
          <v-select
            v-model="cardId"
            :items="cardItems"
            item-title="title"
            item-value="value"
            :label="tm('preview.card')"
            density="compact"
            clearable
          />
        </v-col>
        <v-col cols="12" md="7" class="d-flex align-center">
          <v-btn variant="tonal" color="primary" :loading="loading" @click="run">
            {{ tm("preview.run") }}
          </v-btn>
          <span class="ms-3 text-caption text-medium-emphasis">{{ tm("preview.hint") }}</span>
        </v-col>
        <v-col cols="12">
          <v-textarea
            v-model="message"
            :label="tm('preview.message')"
            :placeholder="tm('preview.messagePlaceholder')"
            rows="3"
            density="compact"
            hide-details
          />
        </v-col>
      </v-row>
    </v-card>

    <template v-if="result">
      <v-row dense class="mb-2">
        <v-col cols="6" md="3">
          <v-card variant="tonal" color="primary" class="pa-3">
            <div class="text-h6">{{ result.system_tokens }}</div>
            <div class="text-caption">{{ tm("preview.systemTokens") }}</div>
          </v-card>
        </v-col>
        <v-col cols="6" md="3">
          <v-card variant="tonal" color="info" class="pa-3">
            <div class="text-h6">{{ result.card_tokens }}</div>
            <div class="text-caption">{{ tm("preview.cardTokens") }}</div>
          </v-card>
        </v-col>
        <v-col cols="6" md="3">
          <v-card variant="tonal" color="success" class="pa-3">
            <div class="text-h6">{{ result.injected_tokens }}</div>
            <div class="text-caption">{{ tm("preview.injected") }}</div>
          </v-card>
        </v-col>
        <v-col cols="6" md="3">
          <v-card variant="tonal" :color="result.skipped.length ? 'warning' : 'grey'" class="pa-3">
            <div class="text-h6">{{ result.skipped.length }}</div>
            <div class="text-caption">{{ tm("preview.skipped") }}</div>
          </v-card>
        </v-col>
      </v-row>

      <v-card variant="outlined" class="pa-4 mb-4">
        <div class="text-subtitle-2 mb-2">{{ tm("preview.trace") }}</div>
        <div v-if="!result.trace.length" class="text-caption text-medium-emphasis">
          {{ tm("preview.noTrace") }}
        </div>
        <v-table v-else density="compact">
          <thead>
            <tr>
              <th>{{ tm("preview.colEntry") }}</th>
              <th>{{ tm("preview.colBook") }}</th>
              <th>{{ tm("preview.colPosition") }}</th>
              <th>{{ tm("preview.colKeywords") }}</th>
              <th class="text-right">{{ tm("unit.tokens") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in result.trace" :key="index">
              <td>{{ item.entry }}</td>
              <td>{{ item.book }}</td>
              <td>
                {{ item.position }}
                <template v-if="item.depth">· {{ tm("preview.depth") }} {{ item.depth }}</template>
              </td>
              <td>{{ item.keywords.join("、") || tm("preview.constant") }}</td>
              <td class="text-right">{{ item.tokens }}</td>
            </tr>
          </tbody>
        </v-table>
        <div v-if="result.skipped.length" class="text-caption text-warning mt-2">
          {{ tm("preview.skippedList") }}:
          {{ result.skipped.map((item) => `${item.entry}(${item.tokens})`).join("、") }}
        </div>
      </v-card>

      <v-card variant="outlined">
        <v-card-title class="text-body-2 py-3">
          {{ tm("preview.finalPrompt") }}
        </v-card-title>
        <v-card-text>
          <pre class="rp-pre">{{ result.system_prompt }}</pre>
        </v-card-text>
      </v-card>
    </template>

    <v-snackbar v-model="snackbar.show" color="error" timeout="4000">{{ snackbar.text }}</v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import { rpApi, type RPPreview } from "@/api/rp";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/rp");

const cards = ref<{ title: string; value: string }[]>([]);
const cardId = ref<string>("");
const message = ref("");
const result = ref<RPPreview | null>(null);
const loading = ref(false);
const snackbar = reactive({ show: false, text: "" });

const cardItems = computed(() => cards.value);

async function run() {
  loading.value = true;
  try {
    result.value = await rpApi.preview({
      card_id: cardId.value || undefined,
      message: message.value,
    });
  } catch (error) {
    snackbar.text = (error as Error).message;
    snackbar.show = true;
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  const list = await rpApi.listCards();
  cards.value = list.cards.map((card) => ({
    title: `${card.name} · ${card.tokens}`,
    value: card.id,
  }));
  if (cards.value.length) cardId.value = cards.value[0].value;
});
</script>

<style scoped>
.rp-pre {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 520px;
  overflow-y: auto;
  font-size: 0.8rem;
  margin: 0;
  background: rgba(128, 128, 128, 0.08);
  padding: 12px;
  border-radius: 6px;
}
</style>
