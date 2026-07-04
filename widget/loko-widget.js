/**
 * LOKO Bot — Embeddable Chat Widget
 *
 * Usage:
 *   <script src="/widget/loko-widget.js"
 *           data-bot-id="YOUR_BOT_ID"
 *           data-api-url="https://your-server.com"
 *           data-api-key="loko_xxx"></script>
 *
 * Features:
 * - Shadow DOM isolation (no CSS conflicts)
 * - SSE streaming for LLM responses
 * - Choice buttons for clarification
 * - Feedback thumbs up/down
 * - Session persistence (sessionStorage)
 * - Light/dark theme via CSS custom properties
 * - Keyboard accessible (ARIA, focus management)
 * - < 50 KB uncompressed
 */

(function () {
  "use strict";

  // --- Config from script tag ---
  const scriptTag = document.currentScript;
  function attr(name) { return scriptTag?.getAttribute(name) || ""; }
  const BOT_ID = attr("data-bot-id");
  const API_URL = attr("data-api-url").replace(/\/$/, "");
  const AUTH_TOKEN = attr("data-api-key");
  const POSITION = attr("data-position") || "bottom-right";
  const THEME = attr("data-theme") || "light";
  const LANG = attr("data-lang") || "fr";

  // --- i18n (P2-1) ---
  const I18N = {
    fr: {
      open_chat: "Ouvrir le chat",
      close_chat: "Fermer le chat",
      placeholder: "\u00C9crire un message\u2026",
      send: "Envoyer",
      useful: "Utile",
      not_useful: "Pas utile",
      online: "En ligne",
      assistant: "Assistant",
      error_start: "Impossible de d\u00E9marrer la conversation.",
      error_message: "Une erreur est survenue.",
    },
    en: {
      open_chat: "Open chat",
      close_chat: "Close chat",
      placeholder: "Type a message\u2026",
      send: "Send",
      useful: "Helpful",
      not_useful: "Not helpful",
      online: "Online",
      assistant: "Assistant",
      error_start: "Unable to start the conversation.",
      error_message: "An error occurred.",
    },
  };
  const t = I18N[LANG] || I18N.fr;

  if (!BOT_ID) {
    console.warn("[LOKO Widget] Missing data-bot-id attribute");
    return;
  }

  const SESSION_KEY = `loko_session_${BOT_ID}`;

  // --- Design tokens (embedded) ---
  const CSS = `
:host {
  --loko-green-50: #EAF6F1;
  --loko-green-100: #CFEBE0;
  --loko-green-500: #0F7D63;
  --loko-green-600: #0C6551;
  --loko-green-700: #0A5142;
  --loko-gray-0: #FFFFFF;
  --loko-gray-25: #FAFBFA;
  --loko-gray-50: #F5F7F6;
  --loko-gray-100: #EBEEED;
  --loko-gray-200: #DBE0DE;
  --loko-gray-300: #C2C9C6;
  --loko-gray-400: #98A19D;
  --loko-gray-600: #545C59;
  --loko-gray-700: #3D4341;
  --loko-gray-800: #292E2C;
  --loko-gray-900: #181B1A;
  --loko-gray-950: #0D0F0E;
  --loko-bronze-500: #A8752D;
  --loko-error-500: #C0432C;

  --loko-font: 'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --loko-font-mono: 'Geist Mono', 'SF Mono', monospace;
  --loko-radius-sm: 6px;
  --loko-radius-md: 10px;
  --loko-radius-xl: 16px;
  --loko-radius-pill: 999px;
  --loko-shadow: 0 4px 24px rgba(0,0,0,0.12);

  all: initial;
  font-family: var(--loko-font);
  font-size: 14px;
  line-height: 1.5;
  color: var(--loko-text);
}

/* Light theme (default) */
:host {
  --loko-bg-page: var(--loko-gray-50);
  --loko-bg-card: var(--loko-gray-0);
  --loko-bg-sunken: var(--loko-gray-25);
  --loko-text: var(--loko-gray-700);
  --loko-text-secondary: var(--loko-gray-600);
  --loko-text-tertiary: var(--loko-gray-400);
  --loko-text-on-brand: var(--loko-gray-0);
  --loko-border: var(--loko-gray-200);
  --loko-border-subtle: var(--loko-gray-100);
  --loko-brand: var(--loko-green-500);
  --loko-brand-tint: var(--loko-green-50);
}

:host([data-theme="dark"]) {
  --loko-bg-page: var(--loko-gray-950);
  --loko-bg-card: var(--loko-gray-900);
  --loko-bg-sunken: var(--loko-gray-800);
  --loko-text: var(--loko-gray-100);
  --loko-text-secondary: var(--loko-gray-300);
  --loko-text-tertiary: var(--loko-gray-400);
  --loko-text-on-brand: var(--loko-gray-0);
  --loko-border: var(--loko-gray-700);
  --loko-border-subtle: var(--loko-gray-800);
  --loko-brand: var(--loko-green-500);
  --loko-brand-tint: var(--loko-green-700);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

.loko-container {
  position: fixed;
  z-index: 999999;
  bottom: 24px;
  right: 24px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
  pointer-events: none;
}

.loko-container > * { pointer-events: auto; }

/* Launcher button */
.loko-launcher {
  width: 56px; height: 56px;
  border-radius: var(--loko-radius-xl);
  border: none;
  background: var(--loko-brand);
  color: var(--loko-text-on-brand);
  box-shadow: var(--loko-shadow);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: transform 200ms ease;
  position: relative;
}
.loko-launcher:hover { transform: scale(1.05); }
.loko-launcher:focus-visible { outline: 2px solid var(--loko-brand); outline-offset: 2px; }

.loko-launcher .loko-badge {
  position: absolute; top: -2px; right: -2px;
  min-width: 18px; height: 18px; padding: 0 4px;
  border-radius: var(--loko-radius-pill);
  background: var(--loko-bronze-500);
  color: #fff;
  font-family: var(--loko-font-mono);
  font-size: 10px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
  border: 2px solid var(--loko-bg-card);
}

/* Chat window */
.loko-window {
  width: 380px;
  max-height: min(560px, calc(100vh - 120px));
  border-radius: var(--loko-radius-xl);
  background: var(--loko-bg-card);
  border: 1px solid var(--loko-border-subtle);
  box-shadow: var(--loko-shadow);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.loko-window.loko-hidden { display: none; }

/* Header */
.loko-header {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--loko-border-subtle);
}
.loko-header-title { font-size: 14px; font-weight: 600; color: var(--loko-text); }
.loko-header-status {
  font-size: 11.5px; color: var(--loko-text-tertiary);
  display: flex; align-items: center; gap: 5px;
}
.loko-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--loko-brand); }

/* Messages area */
.loko-messages {
  flex: 1;
  padding: 16px;
  display: flex; flex-direction: column; gap: 12px;
  overflow-y: auto;
  background: var(--loko-bg-page);
}

/* Bubbles */
.loko-bubble {
  max-width: 82%;
  padding: 10px 14px;
  font-size: 13.5px;
  line-height: 1.5;
  word-wrap: break-word;
}
.loko-bubble-bot {
  align-self: flex-start;
  border-radius: 4px 14px 14px 14px;
  background: var(--loko-bg-sunken);
  color: var(--loko-text);
  border: 1px solid var(--loko-border-subtle);
}
.loko-bubble-user {
  align-self: flex-end;
  border-radius: 14px 4px 14px 14px;
  background: var(--loko-brand);
  color: var(--loko-text-on-brand);
}
.loko-bubble a { color: inherit; text-decoration: underline; }

/* Choice buttons */
.loko-choices {
  display: flex; flex-wrap: wrap; gap: 8px;
  padding-left: 2px;
}
.loko-choice-btn {
  padding: 8px 14px;
  border-radius: var(--loko-radius-pill);
  border: 1px solid var(--loko-border);
  background: var(--loko-bg-card);
  color: var(--loko-text);
  font-size: 13px; font-weight: 500;
  cursor: pointer;
  font-family: var(--loko-font);
  transition: border-color 150ms, background 150ms;
}
.loko-choice-btn:hover:not(:disabled) {
  border-color: var(--loko-brand);
}
.loko-choice-btn:disabled { opacity: 0.45; cursor: default; }
.loko-choice-btn.loko-selected {
  border-color: var(--loko-brand);
  background: var(--loko-brand-tint);
  color: var(--loko-green-700);
  opacity: 1;
}

/* Streaming dots */
.loko-dots {
  display: inline-flex; gap: 5px;
  padding: 11px 14px;
  border-radius: 4px 14px 14px 14px;
  background: var(--loko-bg-sunken);
  border: 1px solid var(--loko-border-subtle);
  align-self: flex-start;
}
.loko-dots span {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--loko-text-tertiary);
  animation: loko-pulse 1.1s ease-in-out infinite;
}
.loko-dots span:nth-child(2) { animation-delay: 0.15s; }
.loko-dots span:nth-child(3) { animation-delay: 0.3s; }
@keyframes loko-pulse {
  0%, 100% { opacity: 0.3; }
  40% { opacity: 0.9; }
}

/* Feedback */
.loko-feedback {
  display: flex; gap: 4px; margin-top: 4px;
  align-self: flex-start;
}
.loko-feedback button {
  width: 28px; height: 28px;
  border-radius: var(--loko-radius-sm);
  border: 1px solid var(--loko-border);
  background: transparent;
  cursor: pointer;
  font-size: 14px;
  display: flex; align-items: center; justify-content: center;
  color: var(--loko-text-tertiary);
  transition: border-color 150ms;
}
.loko-feedback button:hover { border-color: var(--loko-brand); color: var(--loko-text); }
.loko-feedback button.loko-fb-active {
  border-color: var(--loko-brand);
  background: var(--loko-brand-tint);
  color: var(--loko-brand);
}

/* Input area */
.loko-input-area {
  display: flex; gap: 8px;
  padding: 12px;
  border-top: 1px solid var(--loko-border-subtle);
}
.loko-input {
  flex: 1;
  border: 1px solid var(--loko-border);
  border-radius: var(--loko-radius-pill);
  padding: 9px 14px;
  font-size: 13.5px;
  font-family: var(--loko-font);
  background: var(--loko-bg-card);
  color: var(--loko-text);
  outline: none;
}
.loko-input:focus { border-color: var(--loko-brand); }
.loko-input::placeholder { color: var(--loko-text-tertiary); }

.loko-send {
  width: 36px; height: 36px;
  border-radius: 50%;
  border: none;
  background: var(--loko-brand);
  color: var(--loko-text-on-brand);
  cursor: pointer;
  font-size: 16px;
  display: flex; align-items: center; justify-content: center;
}
.loko-send:disabled { opacity: 0.5; cursor: default; }

/* Sources */
.loko-sources {
  font-size: 11.5px;
  color: var(--loko-text-tertiary);
  font-family: var(--loko-font-mono);
  margin-top: 4px;
  padding-left: 4px;
}
.loko-sources a {
  color: var(--loko-brand);
  text-decoration: none;
}
.loko-sources a:hover { text-decoration: underline; }
`;

  // --- Widget Web Component ---
  class LokoWidget extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._open = false;
      this._session = null;
      this._messages = [];
      this._streaming = false;
      this._streamBuffer = "";
    }

    connectedCallback() {
      this.setAttribute("data-theme", THEME);
      this._render();
      this._restoreSession();
    }

    // --- API ---

    async _createSession() {
      try {
        const res = await this._fetch(`/api/v1/bot/${BOT_ID}/sessions`, {
          method: "POST",
        });
        const data = await res.json();
        this._session = {
          id: data.session_id,
          botId: data.bot_id,
          state: data.state,
        };
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(this._session));

        for (const evt of data.events || []) {
          this._handleSSEEvent(evt.event, evt.data);
        }
        this._renderMessages();
      } catch (err) {
        console.error("[LOKO Widget] Failed to create session:", err);
        this._addBotMessage(t.error_start);
      }
    }

    async _sendMessage(text, type = "text") {
      if (!this._session || this._streaming) return;

      this._addUserMessage(text);
      this._streaming = true;
      this._streamBuffer = "";
      this._renderMessages();

      try {
        const res = await this._fetch(
          `/api/v1/bot/${BOT_ID}/sessions/${this._session.id}/messages`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, type }),
          }
        );

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          let eventType = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith("data: ") && eventType) {
              try {
                const data = JSON.parse(line.slice(6));
                this._handleSSEEvent(eventType, data);
              } catch (e) {
                /* skip parse errors */
              }
              eventType = "";
            }
          }
        }

        // Finalize streaming bubble
        if (this._streamBuffer) {
          this._addBotMessage(this._streamBuffer, { streaming: false });
          this._streamBuffer = "";
        }
      } catch (err) {
        console.error("[LOKO Widget] Message error:", err);
        this._addBotMessage(t.error_message);
      } finally {
        this._streaming = false;
        this._renderMessages();
      }
    }

    async _sendFeedback(turnId, rating) {
      if (!this._session) return;
      try {
        await this._fetch(
          `/api/v1/bot/${BOT_ID}/sessions/${this._session.id}/feedback`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ turn_id: turnId, rating }),
          }
        );
      } catch (err) {
        console.error("[LOKO Widget] Feedback error:", err);
      }
    }

    _fetch(path, options = {}) {
      const headers = { ...(options.headers || {}) };
      if (AUTH_TOKEN) {
        headers["Authorization"] = `Bearer ${AUTH_TOKEN}`;
      }
      return fetch(`${API_URL}${path}`, { ...options, headers });
    }

    // --- SSE Event handling ---

    _handleSSEEvent(eventType, data) {
      switch (eventType) {
        case "template":
          this._addBotMessage(data.content, {
            buttons: data.buttons,
            templateKey: data.template_key,
          });
          break;

        case "generation_delta":
          this._streamBuffer += data.token || "";
          this._updateStreamingBubble();
          break;

        case "sources":
          if (data.sources?.length) {
            const last = this._messages[this._messages.length - 1];
            if (last && last.from === "bot") {
              last.sources = data.sources;
            }
          }
          break;

        case "state":
          if (this._session) {
            this._session.state = data.state;
          }
          break;

        case "end_of_turn":
          break;

        case "traces":
          // Available for debug but not displayed in widget
          break;
      }
    }

    // --- Message management ---

    _addBotMessage(text, opts = {}) {
      this._messages.push({
        id: "m_" + Math.random().toString(36).slice(2, 10),
        from: "bot",
        text,
        buttons: opts.buttons || null,
        selectedButton: null,
        sources: opts.sources || null,
        feedback: null,
        templateKey: opts.templateKey || null,
        streaming: opts.streaming || false,
      });
      this._renderMessages();
    }

    _addUserMessage(text) {
      this._messages.push({
        id: "m_" + Math.random().toString(36).slice(2, 10),
        from: "user",
        text,
      });
      this._renderMessages();
    }

    _updateStreamingBubble() {
      // Update the last bot message or create a streaming one
      const last = this._messages[this._messages.length - 1];
      if (last && last.streaming) {
        last.text = this._streamBuffer;
      } else {
        this._messages.push({
          id: "m_" + Math.random().toString(36).slice(2, 10),
          from: "bot",
          text: this._streamBuffer,
          streaming: true,
          feedback: null,
        });
      }
      this._renderMessages();
    }

    _restoreSession() {
      const saved = sessionStorage.getItem(SESSION_KEY);
      if (saved) {
        try {
          this._session = JSON.parse(saved);
        } catch {
          sessionStorage.removeItem(SESSION_KEY);
        }
      }
    }

    // --- Rendering ---

    _render() {
      const shadow = this.shadowRoot;
      shadow.innerHTML = "";

      const style = document.createElement("style");
      style.textContent = CSS;
      shadow.appendChild(style);

      const container = document.createElement("div");
      container.className = "loko-container";

      // Chat window
      const win = document.createElement("div");
      win.className = "loko-window loko-hidden";
      win.setAttribute("role", "dialog");
      win.setAttribute("aria-label", "Chat assistant");
      this._window = win;

      // Header
      const header = document.createElement("div");
      header.className = "loko-header";
      header.innerHTML = `
        <svg width="26" height="26" viewBox="0 0 64 64">
          <rect x="1" y="1" width="62" height="62" rx="14" fill="var(--loko-brand)"/>
          <circle cx="32" cy="32" r="12" fill="var(--loko-text-on-brand)"/>
        </svg>
        <div style="flex:1">
          <div class="loko-header-title">${t.assistant}</div>
          <div class="loko-header-status"><span class="loko-dot"></span>${t.online}</div>
        </div>
      `;
      win.appendChild(header);

      // Messages
      const msgs = document.createElement("div");
      msgs.className = "loko-messages";
      msgs.setAttribute("role", "log");
      msgs.setAttribute("aria-live", "polite");
      this._messagesEl = msgs;
      win.appendChild(msgs);

      // Input
      const inputArea = document.createElement("div");
      inputArea.className = "loko-input-area";

      const input = document.createElement("input");
      input.className = "loko-input";
      input.placeholder = t.placeholder;
      input.setAttribute("aria-label", "Message");
      this._input = input;

      const send = document.createElement("button");
      send.className = "loko-send";
      send.innerHTML = "&#8594;";
      send.setAttribute("aria-label", t.send);
      this._sendBtn = send;

      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          this._onSend();
        }
      });
      send.addEventListener("click", () => this._onSend());

      inputArea.appendChild(input);
      inputArea.appendChild(send);
      win.appendChild(inputArea);

      container.appendChild(win);

      // Launcher
      const launcher = document.createElement("button");
      launcher.className = "loko-launcher";
      launcher.setAttribute("aria-label", t.open_chat);
      launcher.innerHTML = `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;
      launcher.addEventListener("click", () => this._toggle());
      this._launcher = launcher;

      container.appendChild(launcher);
      shadow.appendChild(container);
    }

    _toggle() {
      this._open = !this._open;
      this._window.classList.toggle("loko-hidden", !this._open);
      this._launcher.setAttribute(
        "aria-label",
        this._open ? t.close_chat : t.open_chat
      );

      if (this._open) {
        this._launcher.innerHTML = `<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M4 4L16 16M16 4L4 16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;

        if (!this._session) {
          this._createSession();
        }

        setTimeout(() => this._input?.focus(), 100);
      } else {
        this._launcher.innerHTML = `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;
      }
    }

    _onSend() {
      const text = this._input?.value?.trim();
      if (!text || this._streaming) return;
      this._input.value = "";
      this._sendMessage(text);
    }

    _renderMessages() {
      const el = this._messagesEl;
      if (!el) return;

      el.innerHTML = "";

      for (const msg of this._messages) {
        if (msg.from === "user") {
          const bubble = document.createElement("div");
          bubble.className = "loko-bubble loko-bubble-user";
          bubble.textContent = msg.text;
          el.appendChild(bubble);
        } else {
          const wrapper = document.createElement("div");
          wrapper.style.cssText =
            "display:flex;flex-direction:column;align-items:flex-start;gap:4px;";

          const bubble = document.createElement("div");
          bubble.className = "loko-bubble loko-bubble-bot";
          bubble.innerHTML = this._formatText(msg.text);
          wrapper.appendChild(bubble);

          // Buttons
          if (msg.buttons && msg.buttons.length > 0) {
            const choices = document.createElement("div");
            choices.className = "loko-choices";
            for (const opt of msg.buttons) {
              const btn = document.createElement("button");
              btn.className = "loko-choice-btn";
              btn.textContent = opt;
              if (msg.selectedButton) {
                btn.disabled = true;
                if (msg.selectedButton === opt) {
                  btn.classList.add("loko-selected");
                }
              } else {
                btn.addEventListener("click", () => {
                  msg.selectedButton = opt;
                  this._sendMessage(opt, "button_click");
                });
              }
              choices.appendChild(btn);
            }
            wrapper.appendChild(choices);
          }

          // Sources
          if (msg.sources && msg.sources.length > 0) {
            const src = document.createElement("div");
            src.className = "loko-sources";
            src.innerHTML = msg.sources
              .map(
                (s) =>
                  `<a href="${this._safeUrl(s.url)}" target="_blank" rel="noopener noreferrer">${this._escapeHtml(s.title || s.url)}</a>`
              )
              .join(" \u00B7 ");
            wrapper.appendChild(src);
          }

          // Feedback (only for non-streaming bot messages)
          if (!msg.streaming && msg.from === "bot" && !msg.templateKey) {
            const fb = document.createElement("div");
            fb.className = "loko-feedback";

            const up = document.createElement("button");
            up.textContent = "\u{1F44D}";
            up.setAttribute("aria-label", t.useful);
            if (msg.feedback === "positive") up.classList.add("loko-fb-active");
            up.addEventListener("click", () => {
              msg.feedback = "positive";
              this._sendFeedback(msg.id, "positive");
              this._renderMessages();
            });

            const down = document.createElement("button");
            down.textContent = "\u{1F44E}";
            down.setAttribute("aria-label", t.not_useful);
            if (msg.feedback === "negative")
              down.classList.add("loko-fb-active");
            down.addEventListener("click", () => {
              msg.feedback = "negative";
              this._sendFeedback(msg.id, "negative");
              this._renderMessages();
            });

            fb.appendChild(up);
            fb.appendChild(down);
            wrapper.appendChild(fb);
          }

          el.appendChild(wrapper);
        }
      }

      // Streaming indicator
      if (this._streaming && !this._streamBuffer) {
        const dots = document.createElement("div");
        dots.className = "loko-dots";
        dots.innerHTML = "<span></span><span></span><span></span>";
        el.appendChild(dots);
      }

      // Auto-scroll
      el.scrollTop = el.scrollHeight;
    }

    _formatText(text) {
      // Basic markdown: **bold**, links [text](url), newlines
      const self = this;
      return this._escapeHtml(text)
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(
          /\[([^\]]+)\]\(([^)]+)\)/g,
          function(_, label, url) {
            const safe = self._safeUrl(url);
            return '<a href="' + safe + '" target="_blank" rel="noopener noreferrer">' + label + '</a>';
          }
        )
        .replace(/\n/g, "<br>");
    }

    _safeUrl(url) {
      // Only allow http: and https: schemes (P1-1 — XSS prevention)
      try {
        const parsed = new URL(url, location.origin);
        if (parsed.protocol === "https:" || parsed.protocol === "http:") {
          return parsed.href;
        }
      } catch (e) {
        // Invalid URL
      }
      return "#";
    }

    _escapeHtml(str) {
      const div = document.createElement("div");
      div.textContent = str;
      return div.innerHTML;
    }
  }

  // Register the custom element
  if (!customElements.get("loko-widget")) {
    customElements.define("loko-widget", LokoWidget);
  }

  // Auto-insert if script tag has data-bot-id
  if (BOT_ID) {
    const widget = document.createElement("loko-widget");
    document.body.appendChild(widget);
  }
})();
