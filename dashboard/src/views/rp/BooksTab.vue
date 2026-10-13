<template>
  <div>
    <div class="d-flex align-center ga-3 mb-3 flex-wrap">
      <v-btn variant="tonal" color="primary" prepend-icon="mdi-plus" @click="openBookEditor(null)">
        {{ tm("books.create") }}
      </v-btn>
      <v-btn variant="tonal" prepend-icon="mdi-puzzle-outline" @click="openEntry(null)">
        {{ tm("books.newEntry") }}
      </v-btn>
      <v-spacer />
      <v-text-field
        v-model="entryFilter"
        :label="tm('books.filterEntries')"
        density="compact"
        hide-details
        prepend-inner-icon="mdi-filter-outline"
        clearable
        class="rp-filter"
      />
    </div>

    <v-row dense>
      <v-col cols="12" md="3">
        <v-card variant="outlined" class="rp-list">
          <v-list v-model:selected="selectedBook" density="compact" nav>
            <v-list-item
              v-for="book in books"
              :key="book.id"
              :value="book.id"
              :title="book.name"
              :subtitle="`${book.entries} ${tm('unit.entries')} · ${book.constants} ${tm('books.constants')}`"
            />
          </v-list>
          <div v-if="!books.length" class="pa-6 text-center text-medium-emphasis text-body-2">
            {{ tm("books.empty") }}
          </div>
        </v-card>
      </v-col>

      <v-col cols="12" md="9">
        <template v-if="book">
          <v-card variant="outlined" class="pa-4 mb-3">
            <div class="d-flex align-center ga-2 flex-wrap mb-2">
              <h2 class="text-h6">{{ book.name }}</h2>
              <v-spacer />
              <v-btn size="small" variant="text" prepend-icon="mdi-pencil" @click="openBookEditor(book)">
                {{ tm("actions.edit") }}
              </v-btn>
              <v-btn size="small" variant="text" color="error" @click="removeBook">
                {{ tm("actions.delete") }}
              </v-btn>
            </div>
            <div class="text-caption text-medium-emphasis mb-2">{{ book.description }}</div>
            <div class="d-flex ga-4 flex-wrap text-body-2">
              <span>{{ book.entries.length }} {{ tm("unit.entries") }}</span>
              <span>{{ tm("books.budget") }}: {{ book.token_budget }}</span>
              <span>{{ tm("books.scanDepth") }}: {{ book.scan_depth }}</span>
              <span>{{ tm("books.recursion") }}: {{ book.recursion_limit }}</span>
              <v-chip v-if="book.global_scope" size="x-small" color="info">{{ tm("books.global") }}</v-chip>
              <v-chip v-if="!book.enabled" size="x-small" color="warning">{{ tm("books.disabled") }}</v-chip>
            </div>
          </v-card>

          <v-card variant="outlined">
            <v-list v-if="filteredEntries.length" class="rp-entries">
              <v-list-item
                v-for="entry in filteredEntries"
                :key="entry.id"
                :title="entry.comment || tm('books.unnamed')"
                lines="two"
              >
                <template #prepend>
                  <v-icon :color="entry.constant ? 'success' : 'grey-lighten-1'" size="small">
                    {{ entry.constant ? "mdi-pin" : "mdi-bookmark-outline" }}
                  </v-icon>
                </template>
                <v-list-item-subtitle>
                  <span v-if="entry.keywords.length">{{ entry.keywords.join("、") }}</span>
                  <span v-else class="text-medium-emphasis">{{ tm("books.noKeywords") }}</span>
                  · {{ entry.tokens }} {{ tm("unit.tokens") }} ·
                  {{ tm("books.position") }}: {{ entry.position }} · {{ tm("books.priority") }}:
                  {{ entry.priority }}
                  <span v-if="!entry.enabled" class="text-error"> · {{ tm("books.off") }}</span>
                </v-list-item-subtitle>
                <template #append>
                  <v-btn size="x-small" variant="text" @click="openEntry(entry)">
                    {{ tm("actions.edit") }}
                  </v-btn>
                  <v-btn size="x-small" variant="text" color="error" @click="removeEntry(entry)">
                    {{ tm("actions.delete") }}
                  </v-btn>
                </template>
              </v-list-item>
            </v-list>
            <div v-else class="pa-8 text-center text-medium-emphasis">{{ tm("books.noEntries") }}</div>
          </v-card>
        </template>
        <v-card v-else variant="outlined" class="pa-8 text-center text-medium-emphasis">
          {{ tm("books.pick") }}
        </v-card>
      </v-col>
    </v-row>

    <v-dialog v-model="bookDialog" max-width="520">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">
          {{ bookForm.id ? tm("books.edit") : tm("books.create") }}
        </v-card-title>
        <v-card-text>
          <v-text-field v-model="bookForm.name" :label="tm('books.name')" class="mb-2" />
          <v-text-field v-model="bookForm.description" :label="tm('books.description')" class="mb-2" />
          <v-row dense>
            <v-col cols="4">
              <v-text-field v-model.number="bookForm.token_budget" :label="tm('books.budget')" type="number" />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model.number="bookForm.scan_depth" :label="tm('books.scanDepth')" type="number" />
            </v-col>
            <v-col cols="4">
              <v-text-field
                v-model.number="bookForm.recursion_limit"
                :label="tm('books.recursion')"
                type="number"
              />
            </v-col>
          </v-row>
          <v-switch v-model="bookForm.enabled" :label="tm('books.enabled')" hide-details dense />
          <v-switch v-model="bookForm.global_scope" :label="tm('books.globalHint')" hide-details dense />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="bookDialog = false">{{ tm("actions.cancel") }}</v-btn>
          <v-btn variant="tonal" color="primary" :loading="saving" @click="saveBook">
            {{ tm("actions.save") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="entryDialog" width="880">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ tm("books.entryEditor") }}</v-card-title>
        <v-card-text>
          <v-row dense>
            <v-col cols="12" md="6">
              <v-text-field v-model="entryForm.comment" :label="tm('books.entryName')" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-combobox
                v-model="entryForm.keywords"
                :label="tm('books.keywords')"
                multiple
                chips
                small-chips
                closable-chips
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="12">
              <v-textarea v-model="entryForm.content" :label="tm('books.content')" rows="10" auto-grow />
            </v-col>
            <v-col cols="12">
              <v-combobox
                v-model="entryForm.secondary_keywords"
                :label="tm('books.secondary')"
                multiple
                chips
                small-chips
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="6" md="3">
              <v-select
                v-model="entryForm.selective_logic"
                :items="logicItems"
                item-title="title"
                item-value="value"
                :label="tm('books.logic')"
                density="compact"
              />
            </v-col>
            <v-col cols="6" md="3">
              <v-select
                v-model="entryForm.position"
                :items="positionItems"
                item-title="title"
                item-value="value"
                :label="tm('books.position')"
                density="compact"
              />
            </v-col>
            <v-col cols="4" md="2">
              <v-text-field v-model.number="entryForm.priority" :label="tm('books.priority')" type="number" density="compact" />
            </v-col>
            <v-col cols="4" md="2">
              <v-text-field v-model.number="entryForm.depth" :label="tm('books.depth')" type="number" density="compact" />
            </v-col>
            <v-col cols="4" md="2">
              <v-text-field v-model.number="entryForm.order" :label="tm('books.order')" type="number" density="compact" />
            </v-col>
            <v-col cols="6" md="2">
              <v-text-field
                v-model.number="entryForm.cooldown_turns"
                :label="tm('books.cooldown')"
                type="number"
                density="compact"
              />
            </v-col>
            <v-col cols="12" class="d-flex ga-4 flex-wrap">
              <v-switch v-model="entryForm.enabled" :label="tm('books.enabled')" hide-details density="compact" />
              <v-switch v-model="entryForm.constant" :label="tm('books.constant')" hide-details density="compact" />
              <v-switch v-model="entryForm.case_sensitive" :label="tm('books.case')" hide-details density="compact" />
              <v-switch v-model="entryForm.whole_word" :label="tm('books.whole')" hide-details density="compact" />
              <v-switch v-model="entryForm.regex" :label="tm('books.regex')" hide-details density="compact" />
            </v-col>
          </v-row>

          <v-divider class="my-3" />
          <div class="text-caption mb-1">{{ tm("books.testTitle") }}</div>
          <div class="d-flex ga-2 align-start">
            <v-text-field
              v-model="testText"
              :label="tm('books.testSample')"
              density="compact"
              hide-details
              class="flex-grow-1"
            />
            <v-btn variant="tonal" size="small" :loading="testing" @click="runTest">
              {{ tm("books.testRun") }}
            </v-btn>
          </div>
          <div v-if="testResult" class="text-body-2 mt-2">
            <v-chip :color="testResult.fires ? 'success' : 'grey'" size="small" class="me-2">
              {{ testResult.fires ? tm("books.testFires") : tm("books.testSilent") }}
            </v-chip>
            <span class="text-caption">
              {{ tm("books.testMatched") }}: {{ testResult.matched.join("、") || "-" }}
              <template v-if="entryForm.secondary_keywords.length">
                · {{ tm("books.testSecondary") }}: {{ testResult.secondary_matched.join("、") || "-" }}
              </template>
            </span>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="entryDialog = false">{{ tm("actions.cancel") }}</v-btn>
          <v-btn variant="tonal" color="primary" :loading="saving" @click="saveEntry">
            {{ tm("actions.save") }}
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

import { rpApi, type RPBookDetail, type RPBookRow, type RPEntry } from "@/api/rp";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/rp");

const books = ref<RPBookRow[]>([]);
const selectedBook = ref<string[]>([]);
const book = ref<RPBookDetail | null>(null);
const entryFilter = ref("");
const saving = ref(false);
const testing = ref(false);
const bookDialog = ref(false);
const entryDialog = ref(false);
const testText = ref("");
const testResult = ref<{ matched: string[]; secondary_matched: string[]; fires: boolean } | null>(
  null
);
const snackbar = reactive({ show: false, color: "success", text: "" });

const bookForm = reactive({
  id: "",
  name: "",
  description: "",
  token_budget: 2000,
  scan_depth: 3,
  recursion_limit: 1,
  enabled: true,
  global_scope: false,
});

const emptyEntry = (): RPEntry => ({
  comment: "",
  content: "",
  enabled: true,
  keywords: [],
  secondary_keywords: [],
  selective_logic: "and_any",
  case_sensitive: false,
  whole_word: false,
  regex: false,
  constant: false,
  position: "system_tail",
  depth: 0,
  order: 100,
  priority: 20,
  cooldown_turns: 0,
  tags: [],
});

const entryForm = reactive<RPEntry>(emptyEntry());

const logicItems = computed(() =>
  ["and_any", "and_all", "not_any", "not_all"].map((value) => ({ title: tm(`books.logic.${value}`), value }))
);

const positionItems = computed(() =>
  ["system_top", "system_tail", "history_depth"].map((value) => ({
    title: tm(`books.position.${value}`),
    value,
  }))
);

const filteredEntries = computed(() => {
  const all = book.value?.entries ?? [];
  const needle = entryFilter.value.trim().toLowerCase();
  if (!needle) return all;
  return all.filter(
    (entry) =>
      entry.comment.toLowerCase().includes(needle) ||
      entry.content.toLowerCase().includes(needle) ||
      entry.keywords.some((keyword) => keyword.toLowerCase().includes(needle))
  );
});

function notify(text: string, color = "success") {
  snackbar.text = text;
  snackbar.color = color;
  snackbar.show = true;
}

async function loadBooks() {
  books.value = (await rpApi.listBooks()).books;
  if (!selectedBook.value.length && books.value.length) {
    selectedBook.value = [books.value[0].id];
  }
}

async function loadBook(bookId: string) {
  try {
    book.value = await rpApi.bookDetail(bookId);
  } catch (error) {
    notify((error as Error).message, "error");
    book.value = null;
  }
}

watch(selectedBook, (value) => {
  const id = value[0];
  if (id) loadBook(String(id));
});

function openBookEditor(row: RPBookRow | RPBookDetail | null) {
  if (row) {
    bookForm.id = row.id;
    bookForm.name = row.name;
    bookForm.description = row.description;
    bookForm.token_budget = row.token_budget;
    bookForm.scan_depth = row.scan_depth;
    bookForm.recursion_limit = row.recursion_limit;
    bookForm.enabled = row.enabled;
    bookForm.global_scope = row.global_scope;
  } else {
    bookForm.id = "";
    bookForm.name = "";
    bookForm.description = "";
    bookForm.token_budget = 2000;
    bookForm.scan_depth = 3;
    bookForm.recursion_limit = 1;
    bookForm.enabled = true;
    bookForm.global_scope = false;
  }
  bookDialog.value = true;
}

async function saveBook() {
  saving.value = true;
  try {
    const { id, ...fields } = bookForm;
    await rpApi.saveBook(id ? { book_id: id, book: fields } : { book: fields });
    bookDialog.value = false;
    await loadBooks();
    if (book.value) await loadBook(book.value.id);
    notify(tm("books.saved"));
  } catch (error) {
    notify((error as Error).message, "error");
  } finally {
    saving.value = false;
  }
}

async function removeBook() {
  if (!book.value) return;
  try {
    await rpApi.deleteBook(book.value.id);
    book.value = null;
    selectedBook.value = [];
    await loadBooks();
    notify(tm("books.deleted"));
  } catch (error) {
    notify((error as Error).message, "error");
  }
}

function openEntry(entry: RPEntry | null) {
  Object.assign(entryForm, entry ? JSON.parse(JSON.stringify(entry)) : emptyEntry());
  delete entryForm.tokens;
  testResult.value = null;
  entryDialog.value = true;
}

async function saveEntry() {
  if (!book.value) return;
  if (!entryForm.content.trim()) {
    notify(tm("books.contentRequired"), "error");
    return;
  }
  saving.value = true;
  try {
    await rpApi.saveEntry(book.value.id, { ...entryForm });
    entryDialog.value = false;
    await Promise.all([loadBook(book.value.id), loadBooks()]);
    notify(tm("books.saved"));
  } catch (error) {
    notify((error as Error).message, "error");
  } finally {
    saving.value = false;
  }
}

async function removeEntry(entry: RPEntry) {
  if (!book.value || !entry.id) return;
  try {
    await rpApi.deleteEntry(book.value.id, entry.id);
    await Promise.all([loadBook(book.value.id), loadBooks()]);
  } catch (error) {
    notify((error as Error).message, "error");
  }
}

async function runTest() {
  testing.value = true;
  try {
    testResult.value = await rpApi.testEntry({ ...entryForm }, testText.value);
  } catch (error) {
    notify((error as Error).message, "error");
  } finally {
    testing.value = false;
  }
}

onMounted(loadBooks);
</script>

<style scoped>
.rp-filter {
  max-width: 280px;
}

.rp-list {
  max-height: 560px;
  overflow-y: auto;
}

.rp-entries {
  max-height: 560px;
  overflow-y: auto;
}
</style>
