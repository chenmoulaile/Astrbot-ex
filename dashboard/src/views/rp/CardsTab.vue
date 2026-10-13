<template>
  <div>
    <div class="d-flex align-center ga-3 mb-3 flex-wrap">
      <v-text-field
        v-model="keyword"
        :label="tm('cards.search')"
        density="compact"
        hide-details
        prepend-inner-icon="mdi-magnify"
        class="rp-search"
        clearable
        @update:model-value="loadCards"
      />
      <v-btn variant="tonal" color="primary" prepend-icon="mdi-plus" @click="createDialog = true">
        {{ tm("cards.create") }}
      </v-btn>
      <v-btn variant="text" icon="mdi-refresh" :loading="loading" @click="loadCards" />
    </div>

    <v-row dense>
      <v-col cols="12" md="4">
        <v-card variant="outlined" class="rp-list">
          <v-progress-linear v-if="loading" indeterminate />
          <v-list v-if="cards.length" v-model:selected="selectedId" nav>
            <v-list-item
              v-for="card in cards"
              :key="card.id"
              :value="card.id"
              :title="card.name"
              :subtitle="card.summary"
              lines="two"
            >
              <template #append>
                <div class="text-caption text-right">
                  <div>{{ card.tokens }} {{ tm("unit.tokens") }}</div>
                  <div class="text-medium-emphasis">
                    {{ Object.keys(card.variants).length }} {{ tm("unit.variants") }}
                  </div>
                </div>
              </template>
            </v-list-item>
          </v-list>
          <div v-else class="pa-6 text-center text-medium-emphasis text-body-2">
            {{ tm("cards.empty") }}
          </div>
        </v-card>
      </v-col>

      <v-col cols="12" md="8">
        <v-card v-if="detail" variant="outlined" class="pa-4">
          <div class="d-flex align-center ga-2 mb-2 flex-wrap">
            <h2 class="text-h6">{{ detail.name }}</h2>
            <v-chip
              v-for="(variant, key) in detail.variants"
              :key="key"
              :color="key === detail.active_variant ? 'primary' : undefined"
              :variant="key === detail.active_variant ? 'flat' : 'tonal'"
              size="small"
              @click="switchVariant(String(key))"
            >
              {{ variant.label }} · {{ variant.tokens }}
            </v-chip>
            <v-spacer />
            <v-btn size="small" variant="text" color="error" @click="confirmDelete = true">
              {{ tm("cards.delete") }}
            </v-btn>
          </div>
          <p class="text-body-2 text-medium-emphasis">{{ detail.summary }}</p>
          <div class="text-caption mb-3">
            {{ tm("cards.persona") }}:
            <code>{{ detail.persona_id || "-" }}</code>
            · {{ tm("cards.source") }}: {{ activeVariant?.source_path || "-" }}
          </div>

          <div class="d-flex ga-2 align-center mb-3">
            <v-text-field
              v-model="bindUmo"
              :label="tm('cards.bindUmo')"
              density="compact"
              hide-details
              class="flex-grow-1"
              placeholder="aiocqhttp:GroupMessage:123456"
            />
            <v-btn size="small" variant="tonal" color="primary" :loading="saving" @click="applyBind">
              {{ tm("cards.bind") }}
            </v-btn>
          </div>

          <div class="rp-section-title">{{ tm("cards.bindBooks") }}</div>
          <v-select
            v-model="boundBooks"
            :items="bookItems"
            item-title="title"
            item-value="value"
            multiple
            chips
            dense
            hide-details
            class="mb-4"
            @update:model-value="saveBindings"
          />

          <div class="rp-section-title">{{ tm("cards.blocks") }}</div>
          <v-list density="compact" class="rp-blocks">
            <v-list-item v-for="block in activeVariant?.blocks" :key="block.id">
              <template #prepend>
                <v-switch
                  :model-value="block.enabled"
                  hide-details
                  density="compact"
                  color="primary"
                  @update:model-value="toggleBlock(block, Boolean($event))"
                />
              </template>
              <v-list-item-title>{{ block.title }}</v-list-item-title>
              <v-list-item-subtitle>
                {{ block.tokens }} {{ tm("unit.tokens") }} · {{ block.chars }} {{ tm("unit.chars") }}
                <span v-if="block.kind === 'opening'" class="text-info"> · {{ tm("cards.opening") }}</span>
              </v-list-item-subtitle>
              <template #append>
                <v-btn size="x-small" variant="text" @click="viewBlock(block)">
                  {{ tm("cards.view") }}
                </v-btn>
              </template>
            </v-list-item>
          </v-list>

          <div class="rp-section-title mt-4">{{ tm("cards.greetings") }}</div>
          <v-expansion-panels v-if="activeVariant?.greetings.length" variant="accordion" flat>
            <v-expansion-panel v-for="greeting in activeVariant.greetings" :key="greeting.id">
              <v-expansion-panel-title>
                {{ greeting.title }}
                <span class="text-caption text-medium-emphasis ms-2">{{ greeting.tokens }}</span>
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <pre class="rp-pre">{{ greeting.content }}</pre>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
          <div v-else class="text-caption text-medium-emphasis">{{ tm("cards.noGreetings") }}</div>
        </v-card>

        <v-card v-else variant="outlined" class="pa-8 text-center text-medium-emphasis">
          {{ tm("cards.pick") }}
        </v-card>
      </v-col>
    </v-row>

    <v-dialog v-model="blockDialog" max-width="820">
      <v-card v-if="blockDialogCard">
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ blockDialogCard.title }}</v-card-title>
        <v-card-text>
          <v-textarea
            v-model="blockDraft"
            :label="tm('cards.editContent')"
            rows="18"
            density="compact"
            auto-grow
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="blockDialog = false">{{ tm("actions.cancel") }}</v-btn>
          <v-btn variant="tonal" color="primary" :loading="saving" @click="saveBlockContent">
            {{ tm("actions.save") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="createDialog" max-width="460">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ tm("cards.create") }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="createForm.name" :label="tm('cards.name')" class="mb-2" />
          <v-text-field v-model="createForm.summary" :label="tm('cards.summary')" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="createDialog = false">{{ tm("actions.cancel") }}</v-btn>
          <v-btn variant="tonal" color="primary" :loading="saving" @click="createCard">
            {{ tm("actions.create") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="confirmDelete" max-width="420">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ tm("cards.deleteTitle") }}</v-card-title>
        <v-card-text>{{ tm("cards.deleteBody", { name: detail?.name || "" }) }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="confirmDelete = false">{{ tm("actions.cancel") }}</v-btn>
          <v-btn variant="tonal" color="error" :loading="saving" @click="deleteCard">
            {{ tm("actions.delete") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";

import { rpApi, type RPBlock, type RPCard, type RPBookRow } from "@/api/rp";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/rp");

const cards = ref<RPCard[]>([]);
const books = ref<RPBookRow[]>([]);
const detail = ref<RPCard | null>(null);
const selectedId = ref<string[]>([]);
const keyword = ref("");
const loading = ref(false);
const saving = ref(false);
const blockDialog = ref(false);
const createDialog = ref(false);
const confirmDelete = ref(false);
const blockDraft = ref("");
const blockDialogCard = ref<RPBlock | null>(null);
const boundBooks = ref<string[]>([]);
const bindUmo = ref("");
const createForm = reactive({ name: "", summary: "" });
const snackbar = reactive({ show: false, color: "success", text: "" });

const activeVariant = computed(() =>
  detail.value ? detail.value.variants[detail.value.active_variant] : null
);

const bookItems = computed(() =>
  books.value.map((book) => ({ title: `${book.name} (${book.entries})`, value: book.id }))
);

function notify(text: string, color = "success") {
  snackbar.text = text;
  snackbar.color = color;
  snackbar.show = true;
}

async function loadCards() {
  loading.value = true;
  try {
    cards.value = (await rpApi.listCards(keyword.value)).cards;
  } catch (error) {
    notify((error as Error).message, "error");
  } finally {
    loading.value = false;
  }
}

async function loadDetail(cardId: string) {
  try {
    detail.value = await rpApi.cardDetail(cardId);
    boundBooks.value = [...detail.value.world_book_ids];
  } catch (error) {
    notify((error as Error).message, "error");
  }
}

watch(selectedId, (value) => {
  const id = value[0];
  if (id) loadDetail(String(id));
});

async function switchVariant(key: string) {
  if (!detail.value || key === detail.value.active_variant) return;
  saving.value = true;
  try {
    const result = await rpApi.saveCard({ card_id: detail.value.id, card: { active_variant: key } });
    detail.value = result.card;
    notify(tm("cards.variantSwitched"));
  } catch (error) {
    notify((error as Error).message, "error");
  } finally {
    saving.value = false;
  }
}

async function toggleBlock(block: RPBlock, enabled: boolean) {
  if (!detail.value) return;
  block.enabled = enabled;
  try {
    const result = await rpApi.saveCard({
      card_id: detail.value.id,
      variant: detail.value.active_variant,
      blocks: [{ id: block.id, enabled }],
    });
    detail.value = result.card;
  } catch (error) {
    notify((error as Error).message, "error");
    block.enabled = !enabled;
  }
}

function viewBlock(block: RPBlock) {
  blockDialogCard.value = block;
  blockDraft.value = block.content || "";
  blockDialog.value = true;
}

async function saveBlockContent() {
  if (!detail.value || !blockDialogCard.value) return;
  saving.value = true;
  try {
    const result = await rpApi.saveCard({
      card_id: detail.value.id,
      variant: detail.value.active_variant,
      blocks: [{ id: blockDialogCard.value.id, content: blockDraft.value }],
    });
    detail.value = result.card;
    blockDialog.value = false;
    notify(tm("cards.saved"));
  } catch (error) {
    notify((error as Error).message, "error");
  } finally {
    saving.value = false;
  }
}

async function saveBindings(value: unknown) {
  if (!detail.value) return;
  const ids = Array.isArray(value) ? value.map((item) => String(item)) : [];
  try {
    const result = await rpApi.saveCard({
      card_id: detail.value.id,
      card: { world_book_ids: ids },
    });
    detail.value = result.card;
    notify(tm("cards.saved"));
  } catch (error) {
    notify((error as Error).message, "error");
  }
}

async function applyBind() {
  if (!detail.value || !bindUmo.value.trim()) {
    notify(tm("cards.bindNeedUmo"), "error");
    return;
  }
  saving.value = true;
  try {
    const result = await rpApi.bindCard(bindUmo.value.trim(), detail.value.id);
    notify(`${tm("cards.bindDone")} ${result.persona_id || ""}`);
    detail.value = await rpApi.cardDetail(detail.value.id);
  } catch (error) {
    notify((error as Error).message, "error");
  } finally {
    saving.value = false;
  }
}

async function createCard() {
  if (!createForm.name.trim()) {
    notify(tm("cards.nameRequired"), "error");
    return;
  }
  saving.value = true;
  try {
    const card = await rpApi.createCard({ ...createForm });
    createDialog.value = false;
    createForm.name = "";
    createForm.summary = "";
    await loadCards();
    selectedId.value = [card.id];
  } catch (error) {
    notify((error as Error).message, "error");
  } finally {
    saving.value = false;
  }
}

async function deleteCard() {
  if (!detail.value) return;
  try {
    await rpApi.deleteCard(detail.value.id);
    detail.value = null;
    selectedId.value = [];
    confirmDelete.value = false;
    await loadCards();
    notify(tm("cards.deleted"));
  } catch (error) {
    notify((error as Error).message, "error");
    confirmDelete.value = false;
  }
}

onMounted(async () => {
  books.value = (await rpApi.listBooks()).books;
  await loadCards();
});
</script>

<style scoped>
.rp-search {
  max-width: 320px;
}

.rp-list {
  max-height: 640px;
  overflow-y: auto;
}

.rp-blocks {
  max-height: 380px;
  overflow-y: auto;
}

.rp-section-title {
  font-size: 0.8rem;
  font-weight: 600;
  opacity: 0.75;
  margin-bottom: 6px;
}

.rp-pre {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.82rem;
  margin: 0;
}
</style>
