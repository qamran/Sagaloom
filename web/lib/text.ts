/** Keys and values compare like api/sagaloom/store/canon.py `norm`. */
export const norm = (s: string) =>
  s.replace(/[‘’]/g, "'").replace(/[“”]/g, '"').toLowerCase().split(/\s+/).filter(Boolean).join(" ");
