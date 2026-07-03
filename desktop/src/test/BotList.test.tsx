import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BotList } from "@/pages/bot/BotList";

// Mock i18next
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "fr", changeLanguage: vi.fn() },
  }),
}));

// Mock navigation
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

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

function renderBotList() {
  return render(
    <MemoryRouter>
      <BotList />
    </MemoryRouter>,
  );
}

describe("BotList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("affiche un état vide quand il n'y a pas de bots", async () => {
    mockApi.mockResolvedValueOnce([]);
    renderBotList();

    await waitFor(() => {
      expect(screen.getByText("bot.noBot")).toBeInTheDocument();
    });
  });

  it("affiche la liste des bots", async () => {
    mockApi.mockResolvedValueOnce([
      { bot_id: "1", name: "Bot Alpha", status: "draft" },
      { bot_id: "2", name: "Bot Beta", status: "published" },
    ]);
    renderBotList();

    await waitFor(() => {
      expect(screen.getByText("Bot Alpha")).toBeInTheDocument();
      expect(screen.getByText("Bot Beta")).toBeInTheDocument();
    });
  });

  it("navigue vers le wizard au clic sur un bot", async () => {
    mockApi.mockResolvedValueOnce([
      { bot_id: "abc", name: "Mon Bot", status: "draft" },
    ]);
    renderBotList();

    await waitFor(() => {
      expect(screen.getByText("Mon Bot")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText("Mon Bot"));
    expect(mockNavigate).toHaveBeenCalledWith("/bot/abc/wizard");
  });

  it("affiche le formulaire de création au clic sur le bouton", async () => {
    mockApi.mockResolvedValueOnce([]);
    renderBotList();

    await waitFor(() => {
      expect(screen.getByText("bot.noBot")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText("bot.create"));
    expect(screen.getByPlaceholderText("bot.project.namePlaceholder")).toBeInTheDocument();
  });
});
