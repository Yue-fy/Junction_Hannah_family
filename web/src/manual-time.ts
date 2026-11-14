/**
 * How long the same answer takes by hand: OUR ROUGH ESTIMATES (minutes), for a person who has the drawing set or
 * model open and knows how to read it. Not measured; shown in the customer view as "about N min by hand (estimate)".
 * One row per kind of question, first match wins (matched on the parsed intent and the question text).
 */
export interface ManualTime {
  /** what the person would have to do, shown in the tooltip */
  work: string;
  minutes: number;
  test: (task: string, scope: string, q: string) => boolean;
}

export const MANUAL_TIME: ManualTime[] = [
  { work: "count on the drawing, count in the model, compare and explain the difference", minutes: 30,
    test: (_t, _s, q) => /\b(agree|match|same number|differ|in the model but not|not drawn)\b/i.test(q) },
  { work: "count the elements on every floor of the building and add them up", minutes: 45,
    test: (t, s, q) => t === "count" && (s === "model" || /\b(whole|entire|all floors|building|model)\b/i.test(q)) },
  { work: "count, then multiply by the price", minutes: 15,
    test: (_t, _s, q) => /\b(cost|price|euro|eur|dollar|€|\$)/i.test(q) },
  { work: "find the rooms, read their areas, sort or filter them", minutes: 15,
    test: (_t, _s, q) => /\b(largest|biggest|smallest|larger than|smaller than|more than|less than|each floor|per floor|which)\b/i.test(q) },
  { work: "count the symbols on the sheet, twice to be sure", minutes: 10, test: (t) => t === "count" },
  { work: "add up the room areas of the unit or floor", minutes: 15,
    test: (t, _s, q) => t === "area" && /\b(total|apartment|all|sum)\b/i.test(q) },
  { work: "find the room and read or measure its area", minutes: 5, test: (t) => t === "area" || t === "length" },
  { work: "look up the value in the schedule or title block", minutes: 3, test: (t) => t === "text" },
];

export function manualTime(task = "", scope = "", q = ""): ManualTime {
  return MANUAL_TIME.find((m) => m.test(task, scope, q)) ?? { work: "find and check it on the drawing", minutes: 10, test: () => true };
}
