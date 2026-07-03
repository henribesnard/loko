import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BotWizard } from "@/pages/bot/BotWizard";

// Mock i18next
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts?.count !== undefined) return `${key} (${opts.count})`;
      return key;
    },
    i18n: { language: "fr", changeLanguage: vi.fn() },
  }),
}));

// Mock API
vi.mock("@/lib/api", () => ({
  api: vi.fn(),
  ApiError: class extends Error {
    constructor(public status: number, public body: string, public path: string) {
      super(`API ${status}`);
    }
  },
}));

import { api } from "@/lib/api";
const mockApi = vi.mocked(api);

const MOCK_CONFIG = {
  schema_version: 1,
  bot_id: "test-bot",
  name: "Test Bot",
  channel: "both",
  language: "fr",
  tone_profile: "neutre",
  intents: [],
  journey: {
    seuil_haut: 0.75,
    seuil_bas: 0.45,
    seuil_sous_motif: 0.6,
    max_clarifications: 1,
    max_demandes: 5,
    timeout_inactivite_s: 300,
    retrieval_min_score: 0.35,
    retrieval_min_chunks: 2,
  },
  templates: {},
  knowledge_collection: "",
  confidentiality_filter: ["public"],
  llm: {
    provider: "openai",
    model: "gpt-4o-mini",
    api_key_set: false,
    max_tokens: 600,
    temperature: 0,
    timeout: 60,
  },
  status: "draft",
};

function renderWizard(step = "") {
  const path = step ? `/bot/test-bot/wizard/${step}` : "/bot/test-bot/wizard";
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/bot/:id/wizard" element={<BotWizard />} />
        <Route path="/bot/:id/wizard/:step" element={<BotWizard />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("BotWizard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.mockResolvedValue(MOCK_CONFIG);
  });

  it("affiche le nom du bot et les étapes de navigation", async () => {
    renderWizard();

    await waitFor(() => {
      expect(screen.getByText("Test Bot")).toBeInTheDocument();
    });

    // Step labels should be visible
    expect(screen.getByText(/bot\.wizard\.step1/)).toBeInTheDocument();
    expect(screen.getByText(/bot\.wizard\.step6/)).toBeInTheDocument();
  });

  it("affiche l'étape projet par défaut", async () => {
    renderWizard("project");

    await waitFor(() => {
      expect(screen.getByText("bot.project.title")).toBeInTheDocument();
    });
  });

  it("affiche l'étape parcours", async () => {
    renderWizard("journey");

    await waitFor(() => {
      expect(screen.getByText("bot.journey.title")).toBeInTheDocument();
    });
  });

  it("affiche l'étape messages", async () => {
    renderWizard("messages");

    await waitFor(() => {
      expect(screen.getByText("bot.messages.title")).toBeInTheDocument();
    });
  });

  it("affiche l'étape publication", async () => {
    renderWizard("publish");

    await waitFor(() => {
      expect(screen.getByText("bot.publish.title")).toBeInTheDocument();
    });
  });

  it("affiche les boutons précédent/suivant", async () => {
    renderWizard();

    await waitFor(() => {
      expect(screen.getByText("Test Bot")).toBeInTheDocument();
    });

    expect(screen.getByText("bot.wizard.prev")).toBeInTheDocument();
    expect(screen.getByText("bot.wizard.next")).toBeInTheDocument();
  });
});
