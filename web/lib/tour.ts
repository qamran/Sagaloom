// Get Started checklist flags (design 4.3). Step 1 is set by the entry page; Task 11 sets 2-4.
export const TOUR_KEYS = {
  visited: "sagaloom.tour.visited",
  chatted: "sagaloom.tour.chatted",
  conflict: "sagaloom.tour.conflict",
  myth: "sagaloom.tour.myth",
  dismissed: "sagaloom.tour.dismissed",
} as const;

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
