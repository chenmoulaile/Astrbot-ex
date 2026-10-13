import { httpClient } from "./http";

const BASE = "/api/rp";

export interface RPBlock {
  id: string;
  title: string;
  order: number;
  enabled: boolean;
  kind: string;
  tokens: number;
  chars: number;
  content?: string;
}

export interface RPGreeting {
  id: string;
  title: string;
  tokens: number;
  content?: string;
}

export interface RPCardVariant {
  label: string;
  source_path: string;
  tokens: number;
  blocks: RPBlock[];
  greetings: RPGreeting[];
}

export interface RPCard {
  id: string;
  name: string;
  summary: string;
  tags: string[];
  enabled: boolean;
  active_variant: string;
  persona_id: string | null;
  world_book_ids: string[];
  tokens: number;
  variants: Record<string, RPCardVariant>;
}

export interface RPBookRow {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  global_scope: boolean;
  scan_depth: number;
  recursion_limit: number;
  token_budget: number;
  source_path: string;
  entries: number;
  constants: number;
}

export interface RPEntry {
  id?: string;
  comment: string;
  content: string;
  enabled: boolean;
  keywords: string[];
  secondary_keywords: string[];
  selective_logic: string;
  case_sensitive: boolean;
  whole_word: boolean;
  regex: boolean;
  constant: boolean;
  position: string;
  depth: number;
  order: number;
  priority: number;
  cooldown_turns: number;
  tags: string[];
  source?: string;
  tokens?: number;
}

export interface RPBookDetail extends Omit<RPBookRow, "entries"> {
  entries: RPEntry[];
}

export interface RPTraceItem {
  book: string;
  entry: string;
  position: string;
  depth: number;
  keywords: string[];
  tokens: number;
  recursed: boolean;
}

export interface RPPreview {
  system_prompt: string;
  system_tokens: number;
  card_tokens: number;
  injected_tokens: number;
  trace: RPTraceItem[];
  skipped: { entry: string; tokens: number }[];
  history: { role: string; content: string; injected: boolean }[];
  books: string[];
}

export interface RPOverview {
  cards: number;
  books: number;
  entries: number;
  bound: number;
  storage: string;
  total_tokens: number;
}

export interface RPImportItem {
  path: string;
  kind: string;
  detail: string;
  entries: number;
  blocks: number;
  greetings: number;
  warning: string;
}

export interface RPImportScan {
  summary: string;
  warnings: string[];
  items: RPImportItem[];
  cards: number;
  books: number;
  entries: number;
}

export interface RPImportCommit {
  summary: string;
  warnings: string[];
  synced_personas: number;
}

export interface RPPlatforms {
  platforms: {
    id: string;
    type: string;
    name: string;
    enable: boolean;
    active: boolean;
  }[];
  message_types: string[];
}

interface Envelope<T> {
  status: string;
  message?: string | null;
  data: T;
}

async function request<T>(method: "get" | "post", path: string, body?: unknown): Promise<T> {
  const response =
    method === "get"
      ? await httpClient.get<Envelope<T>>(`${BASE}${path}`)
      : await httpClient.post<Envelope<T>>(`${BASE}${path}`, body ?? {});
  const payload = response.data;
  if (payload.status !== "ok") {
    throw new Error(payload.message || "request_failed");
  }
  return payload.data;
}

export const rpApi = {
  overview: () => request<RPOverview>("get", "/overview"),
  platforms: () => request<RPPlatforms>("get", "/platforms"),
  listCards: (keyword = "") =>
    request<{ cards: RPCard[]; total: number }>("post", "/cards/list", { keyword }),
  cardDetail: (cardId: string) => request<RPCard>("post", "/cards/detail", { card_id: cardId }),
  saveCard: (payload: {
    card_id: string;
    card?: Record<string, unknown>;
    variant?: string;
    blocks?: { id: string; enabled?: boolean; content?: string; title?: string }[];
  }) => request<{ card: RPCard; persona_id: string }>("post", "/cards/save", payload),
  createCard: (payload: { name: string; summary?: string; label?: string }) =>
    request<RPCard>("post", "/cards/create", payload),
  deleteCard: (cardId: string) =>
    request<{ deleted: string }>("post", "/cards/delete", { card_id: cardId }),
  bindCard: (umo: string, cardId: string) =>
    request<{ umo: string; persona_id: string | null }>("post", "/cards/bind", {
      umo,
      card_id: cardId,
    }),
  listBooks: () => request<{ books: RPBookRow[]; total: number }>("post", "/books/list"),
  bookDetail: (bookId: string) => request<RPBookDetail>("post", "/books/detail", { book_id: bookId }),
  saveBook: (payload: { book_id?: string; book: Record<string, unknown> }) =>
    request<{ id: string; name: string; entries: number }>("post", "/books/save", payload),
  deleteBook: (bookId: string) => request<{ deleted: string }>("post", "/books/delete", { book_id: bookId }),
  saveEntry: (bookId: string, entry: RPEntry) =>
    request<{ id: string; tokens: number }>("post", "/books/entry/save", {
      book_id: bookId,
      entry,
    }),
  deleteEntry: (bookId: string, entryId: string) =>
    request<{ deleted: string }>("post", "/books/entry/delete", {
      book_id: bookId,
      entry_id: entryId,
    }),
  testEntry: (entry: RPEntry, text: string) =>
    request<{ matched: string[]; secondary_matched: string[]; fires: boolean }>(
      "post",
      "/books/entry/test",
      { entry, text }
    ),
  importScan: (path: string) => request<RPImportScan>("post", "/import/scan", { path }),
  importCommit: (path: string) =>
    request<RPImportCommit>("post", "/import/commit", { path }),
  preview: (payload: { card_id?: string; message?: string }) =>
    request<RPPreview>("post", "/preview", payload),
  send: (payload: { platform_id: string; message_type: string; target: string; text: string }) =>
    request<{ sent: boolean; umo: string }>("post", "/send", payload),
};
