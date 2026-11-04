import type { EntryType } from "./types";

export const TYPE_ORDER: EntryType[] = ["character", "place", "faction", "rule", "event", "item"];

export const TYPE_LABEL: Record<EntryType, string> = {
  character: "Character",
  place: "Place",
  faction: "Faction",
  rule: "Rule",
  event: "Event",
  item: "Item",
};

export const TYPE_PLURAL: Record<EntryType, string> = {
  character: "Characters",
  place: "Places",
  faction: "Factions",
  rule: "Rules and magic",
  event: "Events",
  item: "Items",
};

// Class names are written out in full so Tailwind can see them.
export const TYPE_TEXT: Record<EntryType, string> = {
  character: "text-character",
  place: "text-place",
  faction: "text-faction",
  rule: "text-rule",
  event: "text-event",
  item: "text-item",
};

export const TYPE_DOT: Record<EntryType, string> = {
  character: "bg-character",
  place: "bg-place",
  faction: "bg-faction",
  rule: "bg-rule",
  event: "bg-event",
  item: "bg-item",
};

export const TYPE_CHIP: Record<EntryType, string> = {
  character: "text-character bg-character-bg border-character-line",
  place: "text-place bg-place-bg border-place-line",
  faction: "text-faction bg-faction-bg border-faction-line",
  rule: "text-rule bg-rule-bg border-rule-line",
  event: "text-event bg-event-bg border-event-line",
  item: "text-item bg-item-bg border-item-line",
};
