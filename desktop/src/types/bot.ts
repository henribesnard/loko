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

export interface ExampleMeta {
  index: number;
  origin: "user" | "assistant" | "import";
}

export interface Intent {
  id: string;
  label: string;
  definition: string;
  examples: string[];
  sub_motifs: SubMotif[];
  is_system: boolean;
  examples_metadata: ExampleMeta[];
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
  // ORC: fine-grained conversation control
  max_tours_par_demande: number;
  max_duree_session_s: number;
  max_tokens_llm_session: number;
  prevenir_avant_derniere_demande: boolean;
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
  // LLM lot: BYO provider per bot
  provider_source: "platform" | "custom";
  provider_type: "openai_compat";
  preset: "openai" | "mistral" | "deepseek" | "ollama" | "vllm" | "autre" | null;
  base_url: string;
  api_key_ref: string;
  api_key_hint: string;
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
  // INT: interrupted generation
  interrupted?: boolean;
  tokens_emitted?: number;
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
  // ORC/GF/PRO new templates
  "avant_derniere_demande",
  "cloture_douce",
  "demande_inappropriee",
  "fin_ferme",
  "maintenance",
] as const;

export const TEMPLATE_VARIABLES = [
  "nom_bot",
  "intentions_gerees",
  "temps_attente",
  "lien_escalade",
  "options",
  // ORC: graceful wind-down
  "resume_demandes",
] as const;

export const JOURNEY_DEFAULTS: JourneyParams = {
  seuil_haut: 0.75,
  seuil_bas: 0.45,
  seuil_sous_motif: 0.60,
  max_clarifications: 1,
  max_demandes: 5,
  timeout_inactivite_s: 300,
  retrieval_min_score: 0.35,
  retrieval_min_chunks: 1,
  // ORC defaults
  max_tours_par_demande: 3,
  max_duree_session_s: 1800,
  max_tokens_llm_session: 8000,
  prevenir_avant_derniere_demande: true,
};

// ---------------------------------------------------------------------------
// Guardrails (GF lot)
// ---------------------------------------------------------------------------

export interface GuardrailRule {
  id: string;
  category: "dangereux" | "donnees_tiers" | "injection" | "juridique_medical" | "custom";
  pattern: string;
  action: "refuser" | "refuser_et_compter" | "escalader";
  enabled: boolean;
  is_system: boolean;
}

export interface GuardrailsConfig {
  enabled: boolean;
  rules: GuardrailRule[];
  max_infractions: number;
  action_apres_max: "fin_ferme" | "escalade";
  seuil_rejet_fort: number;
  block_low_grounding: boolean;
}

// ---------------------------------------------------------------------------
// Escalation (PRO-4)
// ---------------------------------------------------------------------------

export interface EscalationConfig {
  provider: "mock" | "webhook" | "email";
  webhook_url: string;
  webhook_secret_ref: string;
  email_to: string;
  smtp_host: string;
  smtp_port: number;
  smtp_user: string;
  smtp_password_ref: string;
  temps_attente_defaut_min: number;
}

// ---------------------------------------------------------------------------
// Quota (PRO-6)
// ---------------------------------------------------------------------------

export interface QuotaConfig {
  sessions_mois: number;
  messages_mois: number;
  tokens_llm_mois: number;
}

// ---------------------------------------------------------------------------
// Release (PRO-2)
// ---------------------------------------------------------------------------

export interface Release {
  bot_id: string;
  version: number;
  created_at: string;
  config_hash: string;
  model_hash: string;
  index_hash: string;
  active: boolean;
}

// ---------------------------------------------------------------------------
// Alert (PRO-5)
// ---------------------------------------------------------------------------

export interface AlertRule {
  id: string;
  metric: string;
  window_min: number;
  threshold: number;
  direction: "above" | "below";
  channel: "email" | "webhook";
  enabled: boolean;
  silence_min: number;
}

// ---------------------------------------------------------------------------
// Assistant copilot
// ---------------------------------------------------------------------------

export interface Proposal {
  id: string;
  use_case: string;
  sub_mode: string;
  intent_id: string;
  content: string;
  rationale: string;
  confidence: number;
  status: "pending" | "accepted" | "rejected";
}

export interface AssistantRequest {
  use_case: string;
  sub_mode: string;
  intent_id: string;
  context: Record<string, unknown>;
}

export interface AssistantResponse {
  proposals: Proposal[];
  usage: Record<string, number>;
}
