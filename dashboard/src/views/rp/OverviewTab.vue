<template>
  <div>
    <v-row dense class="mb-4">
      <v-col v-for="stat in stats" :key="stat.label" cols="6" md="3">
        <v-card variant="tonal" :color="stat.color" class="pa-3">
          <div class="text-h5">{{ stat.value }}</div>
          <div class="text-caption">{{ stat.label }}</div>
        </v-card>
      </v-col>
    </v-row>

    <v-card variant="outlined" class="mb-4 pa-4">
      <div class="text-subtitle-2 mb-2">{{ tm("overview.storage") }}</div>
      <code class="text-caption">{{ overview?.storage || "-" }}</code>
      <v-divider class="my-3" />
      <ul class="text-body-2 rp-usage">
        <li>{{ tm("overview.usage1") }}</li>
        <li>{{ tm("overview.usage2") }}</li>
        <li>{{ tm("overview.usage3") }}</li>
        <li>{{ tm("overview.usage4") }}</li>
      </ul>
    </v-card>

    <v-card variant="outlined" class="pa-4">
      <div class="text-subtitle-2 mb-3">{{ tm("relay.title") }}</div>
      <v-row dense>
        <v-col cols="12" md="4">
          <v-select
            v-model="sendForm.platform_id"
            :items="platformItems"
            :label="tm('relay.platform')"
            density="compact"
            hide-details
          />
        </v-col>
        <v-col cols="6" md="2">
          <v-select
            v-model="sendForm.message_type"
            :items="typeItems"
            :label="tm('relay.type')"
            density="compact"
            hide-details
          />
        </v-col>
        <v-col cols="6" md="3">
          <v-text-field
            v-model="sendForm.target"
            :label="tm('relay.target')"
            density="compact"
            hide-details
          />
        </v-col>
        <v-col cols="12" md="3" class="d-flex align-center">
          <v-btn
            variant="tonal"
            color="primary"
            :loading="sending"
            :disabled="!canSend"
            @click="sendNow"
          >
            {{ tm("relay.send") }}
          </v-btn>
        </v-col>
        <v-col cols="12">
          <v-textarea
            v-model="sendForm.text"
            :label="tm('relay.text')"
            rows="3"
            density="compact"
            hide-details
          />
        </v-col>
      </v-row>
      <p class="text-caption text-medium-emphasis mt-3 mb-0">{{ tm("relay.hint") }}</p>
    </v-card>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="4000">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import { rpApi, type RPOverview, type RPPlatforms } from "@/api/rp";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/rp");

const overview = ref<RPOverview | null>(null);
const platforms = ref<RPPlatforms>({ platforms: [], message_types: ["FriendMessage", "GroupMessage"] });
const sending = ref(false);
const snackbar = reactive({ show: false, color: "success", text: "" });
const sendForm = reactive({ platform_id: "", message_type: "FriendMessage", target: "", text: "" });

const stats = computed(() => [
  { label: tm("overview.cards"), value: overview.value?.cards ?? 0, color: "primary" },
  { label: tm("overview.books"), value: overview.value?.books ?? 0, color: "info" },
  { label: tm("overview.entries"), value: overview.value?.entries ?? 0, color: "success" },
  { label: tm("overview.bound"), value: overview.value?.bound ?? 0, color: "warning" },
]);

const platformItems = computed(() =>
  platforms.value.platforms.map((item) => ({
    title: `${item.name || item.id}${item.active ? "" : ` · ${tm("relay.offline")}`}`,
    value: item.id,
  }))
);

const typeItems = computed(() =>
  platforms.value.message_types.map((value) => ({
    title: value === "GroupMessage" ? tm("relay.group") : tm("relay.friend"),
    value,
  }))
);

const canSend = computed(
  () => Boolean(sendForm.platform_id && sendForm.target && sendForm.text.trim())
);

function notify(text: string, color = "success") {
  snackbar.text = text;
  snackbar.color = color;
  snackbar.show = true;
}

async function load() {
  try {
    const [ov, pl] = await Promise.all([rpApi.overview(), rpApi.platforms()]);
    overview.value = ov;
    platforms.value = pl;
    if (!sendForm.platform_id && pl.platforms.length) {
      sendForm.platform_id = pl.platforms[0].id;
    }
  } catch (error) {
    notify((error as Error).message, "error");
  }
}

async function sendNow() {
  sending.value = true;
  try {
    const result = await rpApi.send({ ...sendForm });
    notify(`${tm("relay.sent")} ${result.umo}`);
    sendForm.text = "";
  } catch (error) {
    notify((error as Error).message, "error");
  } finally {
    sending.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.rp-usage {
  padding-left: 20px;
  margin: 0;
}

.rp-usage li {
  margin-bottom: 4px;
}
</style>
