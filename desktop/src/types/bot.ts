/**
 * LOKO — TypeScript types mirroring backend Pydantic models.
 */

export type ToneProfile = "formel" | "chaleureux" | "neutre";
export type Channel = "widget" | "api" | "both";
export type BotLanguage = "fr" | "en" | "auto";
export type BotStatus = "draft" | "published";

export interface SubMotif {
  id: string;
  label: string;
  definition: string;
  examples: string[];
}

export interface Intent {
  id: string;
  label: string;
  definition: string;
  examples: string[];
  sub_motifs: SubMotif[];
  is_system: boolean;
}

export interface JourneyParams {
  seuil_haut: number;
  seuil_bas: number;
  seuil_sous_motif: number;
  max_clarifications: number;
  max_demandes: number;
  timeout_inactivite_s: number;
  retrieval_min_score: number;
  retrieval_min_chunks: number;
}

export interface MessageTemplate {
  key: string;
  text_fr: string;
  text_en: string;
  variables: string[];
}

export interface BotLLMConfig {
  provider: string;
  model: string;
  api_key_set: boolean;
  max_tokens: number;
  temperature: number;
  timeout: number;
}

export interface BotConfig {
  schema_version: number;
  bot_id: string;
  name: string;
  channel: Channel;
  language: BotLanguage;
  tone_profile: ToneProfile;
  intents: Intent[];
  journey: JourneyParams;
  templates: Record<string, MessageTemplate>;
  knowledge_collection: string;
  confidentiality_filter: string[];
  llm: BotLLMConfig;
  status: BotStatus;
}

export interface BotListItem {
  bot_id: string;
  name: string;
  status: string;
}

export interface TrainingStatus {
  bot_id: string;
  status: "idle" | "running" | "completed" | "failed";
  step?: string;
  error?: string;
  result?: Record<string, unknown>;
}

export interface EvaluationResult {
  accuracy: number;
  confusion_matrix: Record<string, Record<string, number>>;
  per_class: Record<string, { precision: number; recall: number; f1: number }>;
}

export interface TraceEvent {
  turn_id: string;
  step: string;
  detail: Record<string, unknown>;
  latency_ms: number;
}

export interface Turn {
  turn_id: string;
  role: "user" | "bot" | "system";
  content: string;
  timestamp: string;
  template_key?: string;
  buttons?: string[];
  button_selected?: string;
  intent?: string;
  sub_motif?: string;
  sources?: Array<Record<string, unknown>>;
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface SessionCreateResponse {
  session_id: string;
  bot_id: string;
  state: string;
  events: SSEEvent[];
}

export interface SessionState {
  session_id: string;
  bot_id: string;
  state: string;
  transcript: Turn[];
  current_intent?: string;
  current_sub_motif?: string;
}

export const TEMPLATE_KEYS = [
  "presentation",
  "clarification_inter",
  "clarification_intra",
  "hors_perimetre",
  "enquete_satisfaction",
  "autre_demande",
  "fin",
  "mise_en_relation",
  "timeout",
] as const;

export const TEMPLATE_VARIABLES = [
  "nom_bot",
  "intentions_gerees",
  "temps_attente",
  "lien_escalade",
  "options",
] as const;

export const JOURNEY_DEFAULTS: JourneyParams = {
  seuil_haut: 0.75,
  seuil_bas: 0.45,
  seuil_sous_motif: 0.60,
  max_clarifications: 1,
  max_demandes: 5,
  timeout_inactivite_s: 300,
  retrieval_min_score: 0.35,
  retrieval_min_chunks: 2,
};
