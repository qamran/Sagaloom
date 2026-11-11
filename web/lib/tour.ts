// Get Started checklist flags (design 4.3). Step 1 is set by the entry page; Task 11 sets 2-4.
// Keys carry the signed-in user's id (`sagaloom.tour.<userId>.<step>`), so two accounts in one browser
// keep separate checklists. Before the id is known (and in tests that never set it) there is no id part.
let tourUser: string | null = null;

export function setTourUser(id: string | null): void {
  tourUser = id;
}

const key = (step: string) => (tourUser ? `sagaloom.tour.${tourUser}.${step}` : `sagaloom.tour.${step}`);

export const TOUR_KEYS = {
  get visited() {
    return key("visited");
  },
  get chatted() {
    return key("chatted");
  },
  get conflict() {
    return key("conflict");
  },
  get myth() {
    return key("myth");
  },
  get dismissed() {
    return key("dismissed");
  },
};

export type TourStep = "visited" | "chatted" | "conflict" | "myth";

export const TOUR_EVENT = "sagaloom:tour";

export function readFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

export function markTour(step: TourStep | "dismissed"): void {
  try {
    localStorage.setItem(TOUR_KEYS[step], "1");
  } catch {
    /* storage unavailable: the checklist just will not tick */
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(TOUR_EVENT));
}
