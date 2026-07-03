import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BotPlayground } from "@/pages/bot/BotPlayground";

// Mock i18next
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
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

function renderPlayground() {
  return render(
    <MemoryRouter initialEntries={["/bot/test-bot/playground"]}>
      <Routes>
        <Route path="/bot/:id/playground" element={<BotPlayground />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("BotPlayground", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("affiche le titre et le panneau de trace", async () => {
    // Mock session creation
    mockApi.mockResolvedValueOnce({
      session_id: "sess-1",
      bot_id: "test-bot",
      state: "attente_demande",
      events: [
        {
          event: "template",
          data: { text: "Bonjour, comment puis-je vous aider ?", turn_id: "t1" },
        },
      ],
    });

    renderPlayground();

    await waitFor(() => {
      expect(screen.getByText("bot.playground.title")).toBeInTheDocument();
    });

    // Trace panel
    expect(screen.getByText("bot.playground.trace")).toBeInTheDocument();
  });

  it("affiche le message de bienvenue après création de session", async () => {
    mockApi.mockResolvedValueOnce({
      session_id: "sess-2",
      bot_id: "test-bot",
      state: "attente_demande",
      events: [
        {
          event: "template",
          data: { text: "Bienvenue ! Je suis là pour vous aider.", turn_id: "t1" },
        },
      ],
    });

    renderPlayground();

    await waitFor(() => {
      expect(
        screen.getByText("Bienvenue ! Je suis là pour vous aider."),
      ).toBeInTheDocument();
    });
  });

  it("affiche l'état FSM courant", async () => {
    mockApi.mockResolvedValueOnce({
      session_id: "sess-3",
      bot_id: "test-bot",
      state: "attente_demande",
      events: [],
    });

    renderPlayground();

    await waitFor(() => {
      expect(screen.getByText("attente_demande")).toBeInTheDocument();
    });
  });

  it("affiche un message quand il n'y a pas de traces", async () => {
    mockApi.mockResolvedValueOnce({
      session_id: "sess-4",
      bot_id: "test-bot",
      state: "accueil",
      events: [],
    });

    renderPlayground();

    await waitFor(() => {
      expect(screen.getByText("bot.playground.noTrace")).toBeInTheDocument();
    });
  });
});
