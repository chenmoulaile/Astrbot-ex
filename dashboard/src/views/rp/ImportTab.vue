<template>
  <div>
    <v-card variant="outlined" class="pa-4 mb-4">
      <div class="text-body-2 mb-3">{{ tm("import.hint") }}</div>
      <div class="d-flex ga-2 align-center flex-wrap">
        <v-text-field
          v-model="path"
          :label="tm('import.path')"
          :placeholder="tm('import.pathPlaceholder')"
          density="compact"
          hide-details
          class="flex-grow-1"
          prepend-inner-icon="mdi-folder-text-outline"
        />
        <v-btn variant="tonal" :loading="scanning" @click="scan">{{ tm("import.scan") }}</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="committing"
          :disabled="!scanResult"
          @click="commit"
        >
          {{ tm("import.commit") }}
        </v-btn>
      </div>
    </v-card>

    <v-card v-if="scanResult" variant="outlined" class="pa-4">
      <div class="d-flex align-center ga-3 mb-3 flex-wrap">
        <h2 class="text-h6">{{ tm("import.result") }}</h2>
        <v-chip size="small" color="primary">{{ scanResult.summary }}</v-chip>
      </div>

      <v-alert v-if="scanResult.warnings.length" type="warning" density="compact" class="mb-3">
        <div v-for="warning in scanResult.warnings" :key="warning" class="text-caption">
          {{ warning }}
        </div>
      </v-alert>

      <v-table density="compact" class="rp-table">
        <thead>
          <tr>
            <th>{{ tm("import.colFile") }}</th>
            <th>{{ tm("import.colKind") }}</th>
            <th>{{ tm("import.colDetail") }}</th>
            <th class="text-right">{{ tm("import.colBlocks") }}</th>
            <th class="text-right">{{ tm("import.colGreetings") }}</th>
            <th class="text-right">{{ tm("import.colEntries") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in scanResult.items.slice(0, 300)" :key="item.path + item.kind">
            <td class="rp-file">{{ baseName(item.path) }}</td>
            <td>{{ item.kind }}</td>
            <td>{{ item.detail }}</td>
            <td class="text-right">{{ item.blocks || "" }}</td>
            <td class="text-right">{{ item.greetings || "" }}</td>
            <td class="text-right">{{ item.entries || "" }}</td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <v-card v-else variant="outlined" class="pa-8 text-center text-medium-emphasis">
      {{ tm("import.idle") }}
    </v-card>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="4000">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";

import { rpApi, type RPImportScan } from "@/api/rp";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/rp");

const path = ref("");
const scanResult = ref<RPImportScan | null>(null);
const scanning = ref(false);
const committing = ref(false);
const snackbar = reactive({ show: false, color: "success", text: "" });

function notify(text: string, color = "success") {
  snackbar.text = text;
  snackbar.color = color;
  snackbar.show = true;
}

function baseName(full: string) {
  const parts = full.split(/[\\/]/);
  return parts[parts.length - 1];
}

async function scan() {
  if (!path.value.trim()) {
    notify(tm("import.needPath"), "error");
    return;
  }
  scanning.value = true;
  try {
    scanResult.value = await rpApi.importScan(path.value.trim());
  } catch (error) {
    notify((error as Error).message, "error");
    scanResult.value = null;
  } finally {
    scanning.value = false;
  }
}

async function commit() {
  if (!path.value.trim()) return;
  committing.value = true;
  try {
    const result = await rpApi.importCommit(path.value.trim());
    notify(`${tm("import.done")} ${result.summary}`);
  } catch (error) {
    notify((error as Error).message, "error");
  } finally {
    committing.value = false;
  }
}
</script>

<style scoped>
.rp-table {
  max-height: 460px;
  overflow: auto;
}

.rp-file {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
