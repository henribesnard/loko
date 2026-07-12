/**
 * CSV import/export utilities for bot intents.
 *
 * Format: flat CSV, one row per example.
 * Columns: type, intent_id, label, definition, is_system, example,
 *          sub_motif_id, sub_motif_label, sub_motif_definition
 */
import type { Intent } from "@/types/bot";

const CSV_HEADER =
  "type,intent_id,label,definition,is_system,example,sub_motif_id,sub_motif_label,sub_motif_definition";

// ---------------------------------------------------------------------------
// RFC 4180 helpers
// ---------------------------------------------------------------------------

function escapeField(v: string): string {
  if (v.includes(",") || v.includes('"') || v.includes("\n")) {
    return `"${v.replace(/"/g, '""')}"`;
  }
  return v;
}

function parseLine(line: string): string[] {
  const fields: string[] = [];
  let i = 0;

  while (i <= line.length) {
    if (i === line.length) {
      fields.push("");
      break;
    }
    if (line[i] === '"') {
      let val = "";
      i++; // skip opening quote
      while (i < line.length) {
        if (line[i] === '"') {
          if (i + 1 < line.length && line[i + 1] === '"') {
            val += '"';
            i += 2;
          } else {
            i++; // skip closing quote
            break;
          }
        } else {
          val += line[i];
          i++;
        }
      }
      fields.push(val);
      if (i < line.length && line[i] === ",") i++;
    } else {
      const comma = line.indexOf(",", i);
      if (comma === -1) {
        fields.push(line.substring(i));
        break;
      }
      fields.push(line.substring(i, comma));
      i = comma + 1;
    }
  }
  return fields;
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

/** Serialize intents to CSV. Returns header-only template when array is empty. */
export function exportIntentsToCSV(intents: Intent[]): string {
  const lines: string[] = [CSV_HEADER];

  for (const intent of intents) {
    if (intent.examples.length === 0) {
      lines.push(
        [
          "intent",
          escapeField(intent.id),
          escapeField(intent.label),
          escapeField(intent.definition),
          String(intent.is_system),
          "",
          "",
          "",
          "",
        ].join(","),
      );
    } else {
      for (let idx = 0; idx < intent.examples.length; idx++) {
        lines.push(
          [
            "intent",
            escapeField(intent.id),
            idx === 0 ? escapeField(intent.label) : "",
            idx === 0 ? escapeField(intent.definition) : "",
            idx === 0 ? String(intent.is_system) : "",
            escapeField(intent.examples[idx]),
            "",
            "",
            "",
          ].join(","),
        );
      }
    }

    for (const sm of intent.sub_motifs) {
      if (sm.examples.length === 0) {
        lines.push(
          [
            "sub_motif",
            escapeField(intent.id),
            "",
            "",
            "",
            "",
            escapeField(sm.id),
            escapeField(sm.label),
            escapeField(sm.definition),
          ].join(","),
        );
      } else {
        for (let idx = 0; idx < sm.examples.length; idx++) {
          lines.push(
            [
              "sub_motif",
              escapeField(intent.id),
              "",
              "",
              "",
              escapeField(sm.examples[idx]),
              escapeField(sm.id),
              idx === 0 ? escapeField(sm.label) : "",
              idx === 0 ? escapeField(sm.definition) : "",
            ].join(","),
          );
        }
      }
    }
  }

  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Import (with merge)
// ---------------------------------------------------------------------------

/**
 * Parse CSV and merge with existing intents.
 *
 * - Matching intent_id → update label/definition if non-empty, merge examples
 * - New intent_id → create
 * - Existing intents absent from CSV → preserved unchanged
 */
export function parseIntentsCSV(
  csv: string,
  existingIntents: Intent[],
): Intent[] {
  const lines = csv
    .replace(/^\uFEFF/, "") // strip BOM
    .split(/\r?\n/)
    .filter((l) => l.trim() !== "");
  if (lines.length === 0) throw new Error("Le fichier CSV est vide.");

  if (!lines[0].startsWith("type,intent_id,")) {
    throw new Error(
      "En-tête CSV invalide. Attendu : type,intent_id,label,...",
    );
  }

  // Deep-clone existing intents into a map
  const map = new Map<string, Intent>();
  for (const intent of existingIntents) {
    map.set(intent.id, {
      ...intent,
      examples: [...intent.examples],
      sub_motifs: intent.sub_motifs.map((sm) => ({
        ...sm,
        examples: [...sm.examples],
      })),
    });
  }

  const csvOrder: string[] = [];

  for (let n = 1; n < lines.length; n++) {
    const f = parseLine(lines[n]);
    if (f.length < 9) continue;

    const type = f[0].trim();
    const intentId = f[1].trim();
    if (!intentId) continue;

    if (type === "intent") {
      const label = f[2].trim();
      const definition = f[3].trim();
      const isSystem = f[4].trim();
      const example = f[5].trim();

      if (!map.has(intentId)) {
        map.set(intentId, {
          id: intentId,
          label: label || intentId,
          definition: definition || "",
          examples: [],
          sub_motifs: [],
          is_system: isSystem === "true",
        });
      }

      const intent = map.get(intentId)!;
      if (label) intent.label = label;
      if (definition) intent.definition = definition;
      if (isSystem) intent.is_system = isSystem === "true";
      if (example && !intent.examples.includes(example)) {
        intent.examples.push(example);
      }
      if (!csvOrder.includes(intentId)) csvOrder.push(intentId);
    } else if (type === "sub_motif") {
      const example = f[5].trim();
      const smId = f[6].trim();
      const smLabel = f[7].trim();
      const smDef = f[8].trim();

      if (!smId || !map.has(intentId)) continue;

      const intent = map.get(intentId)!;
      let sm = intent.sub_motifs.find((s) => s.id === smId);

      if (!sm) {
        sm = { id: smId, label: smLabel || smId, definition: smDef || "", examples: [] };
        intent.sub_motifs.push(sm);
      }
      if (smLabel) sm.label = smLabel;
      if (smDef) sm.definition = smDef;
      if (example && !sm.examples.includes(example)) {
        sm.examples.push(example);
      }
    }
  }

  // Build result: existing order first, then new from CSV
  const result: Intent[] = [];
  const seen = new Set<string>();
  for (const intent of existingIntents) {
    result.push(map.get(intent.id)!);
    seen.add(intent.id);
  }
  for (const id of csvOrder) {
    if (!seen.has(id)) {
      result.push(map.get(id)!);
    }
  }
  return result;
}

// ---------------------------------------------------------------------------
// Download helper
// ---------------------------------------------------------------------------

/** Trigger browser download of a CSV string. Adds UTF-8 BOM for Excel. */
export function downloadCSV(content: string, filename: string): void {
  const blob = new Blob(["\uFEFF" + content], {
    type: "text/csv;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
