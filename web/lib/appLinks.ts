"use client";

import { createContext, useContext } from "react";

const AppLinks = createContext(true);

/**
 * Turns off links into app pages (entry citations, course chips) for everything inside: the public
 * home page shows a real ApprovalCard to signed-out visitors, who cannot open those pages.
 */
export const AppLinksProvider = AppLinks.Provider;

/** Whether entries and course notes may link into the app here (true unless a provider says no). */
export const useAppLinks = () => useContext(AppLinks);
