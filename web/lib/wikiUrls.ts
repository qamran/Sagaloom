/** The Fan wiki card's URL check: the same rules and copy as `parse_page_urls`
 * (api/sagaloom/wiki/pages.py). Both sides read the vectors in api/tests/fixtures/wiki_urls.json,
 * so the copy can't drift. The server still normalises and checks again; this only saves a trip. */

export const MAX_URLS = 10;
const SHOWN = 80; // a refused line is quoted back cut to this many characters

const COUNT = `Paste 1 to ${MAX_URLS} page URLs, one per line.`;
const NOT_A_PAGE = (u: string) => `Not a wiki page URL: ${u}. Use a page link such as https://en.wikipedia.org/wiki/Gandalf.`;
const NOT_ALLOWED = (u: string) => `Only Wikipedia and Fandom pages can be imported: ${u}`;
const NOT_ARTICLE = (u: string) => `Only article pages can be imported, not category, file or special pages: ${u}`;
const MIXED = "All URLs in one import must come from the same wiki.";
const TWICE = (u: string) => `This page is listed twice: ${u}`;

const LABEL = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const WIKIPEDIA_PATH = /^\/wiki\/(.+)$/;
const FANDOM_PATH = /^(?:\/([a-z]{2,3}(?:-[a-z]+)?))?\/wiki\/(.+)$/;
const NAMESPACES = new Set([
  "category", "file", "image", "special", "template", "help", "user", "talk", "wikipedia",
  "project", "mediawiki", "portal", "module", "draft", "media",
]);
const NOT_A_LANGUAGE = new Set(["www", "m"]);
const DOMAINS = ["wikipedia.org", "fandom.com"];

class Refused extends Error {}

const shown = (line: string) => Array.from(line).slice(0, SHOWN).join("");

function hostAllowed(url: URL): boolean {
  const host = url.hostname.toLowerCase();
  return (
    url.protocol === "https:" &&
    !url.username &&
    !url.password &&
    (url.port === "" || url.port === "443") &&
    !host.endsWith(".") &&
    DOMAINS.some((d) => host === d || host.endsWith("." + d))
  );
}

function wikiLabel(host: string, domain: string): string | null {
  const suffix = "." + domain;
  if (!host.endsWith(suffix)) return null;
  let label = host.slice(0, -suffix.length);
  if (domain === "wikipedia.org") {
    if (label.endsWith(".m")) label = label.slice(0, -2);
    if (NOT_A_LANGUAGE.has(label)) return null;
  }
  return LABEL.test(label) ? label : null;
}

function isNamespaced(title: string): boolean {
  if (!title.includes(":")) return false;
  let prefix = title.split(":", 1)[0].trim().toLowerCase();
  if (prefix.endsWith(" talk")) prefix = prefix.slice(0, -" talk".length).trim();
  return NAMESPACES.has(prefix);
}

/** The wiki and the page of one line, for the "same wiki" and "listed twice" checks. */
function parseLine(line: string): { wiki: string; page: string } {
  // The browser's parser reads `\` as `/` (WHATWG); the server's does not. So refuse as it does:
  // a `\` in place of `//` leaves no host, a `\` in the host is not an allowed host, and a `\`
  // in the path (the title) the server accepts.
  if (line.includes("\\")) {
    const authority = /^[a-z][a-z0-9+.-]*:\/\/([^/]*)/i.exec(line);
    if (!authority) throw new Refused(NOT_A_PAGE(shown(line)));
    if (authority[1].includes("\\")) throw new Refused(NOT_ALLOWED(shown(line)));
  }
  let url: URL;
  try {
    url = new URL(line);
  } catch {
    throw new Refused(NOT_A_PAGE(shown(line)));
  }
  if (!url.hostname) throw new Refused(NOT_A_PAGE(shown(line)));
  if (!hostAllowed(url)) throw new Refused(NOT_ALLOWED(shown(line)));

  let host = url.hostname.toLowerCase();
  let lang = "";
  let rawTitle: string | undefined;
  const wp = wikiLabel(host, "wikipedia.org");
  if (wp !== null) {
    host = `${wp}.wikipedia.org`;
    rawTitle = WIKIPEDIA_PATH.exec(url.pathname)?.[1];
  } else if (wikiLabel(host, "fandom.com") !== null) {
    const m = FANDOM_PATH.exec(url.pathname);
    rawTitle = m?.[2];
    if (m?.[1]) lang = "/" + m[1];
  }
  if (rawTitle === undefined) throw new Refused(NOT_A_PAGE(shown(line)));

  let title: string;
  try {
    title = decodeURIComponent(rawTitle);
  } catch {
    title = rawTitle;
  }
  title = title.replace(/_/g, " ").trim();
  if (!title) throw new Refused(NOT_A_PAGE(shown(line)));
  if (isNamespaced(title)) throw new Refused(NOT_ARTICLE(shown(line)));
  // MediaWiki folds only the title's first letter.
  return { wiki: host + lang, page: `${host}${lang}/${title.charAt(0).toUpperCase()}${title.slice(1)}` };
}

/** The pasted text as page URLs. `urls` holds the non-blank lines trimmed, as typed (the server
 * normalises); `error` is the first refusal's copy, or null. */
export function checkWikiUrls(text: string): { urls: string[]; error: string | null } {
  const urls = text
    .split(/\r\n|\r|\n/)
    .map((l) => l.trim())
    .filter((l) => l !== "");
  try {
    if (urls.length < 1 || urls.length > MAX_URLS) throw new Refused(COUNT);
    const parsed = urls.map(parseLine);
    if (new Set(parsed.map((p) => p.wiki)).size > 1) throw new Refused(MIXED);
    const seen = new Set<string>();
    parsed.forEach((p, i) => {
      if (seen.has(p.page)) throw new Refused(TWICE(shown(urls[i])));
      seen.add(p.page);
    });
  } catch (e) {
    if (e instanceof Refused) return { urls, error: e.message };
    throw e;
  }
  return { urls, error: null };
}
