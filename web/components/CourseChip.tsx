"use client";

import Link from "next/link";
import { useAppLinks } from "@/lib/appLinks";
import { useCourseNotes, type FeatureCardId } from "@/lib/courseNotes";

/** A small course annotation (R20.8) that links to the matching Studio feature card. */
export function CourseChip({ card, label }: { card: FeatureCardId; label: string }) {
  const [on] = useCourseNotes();
  const links = useAppLinks();
  if (!on || !links) return null;
  return (
    <Link
      href={`/studio?card=${card}#feature-map`}
      aria-label={`Course note: ${label}`}
      className="inline-flex items-center normal-case tracking-normal rounded-full border border-myth bg-panel-3 px-2 py-px text-[11px] text-myth no-underline hover:bg-panel-2 hover:text-myth hover:no-underline"
    >
      {label}
    </Link>
  );
}
