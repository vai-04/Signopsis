// Pipeline E (screen -> sign/voice). The backend's SCREEN mode is planned (screen_parser in the mode
// manager); until POST /api/screen/describe exists, the page structure is read locally from a DOM
// snapshot and phrased with the same short, ordered, action-first style.

/** Snapshot the parts of a page that matter: headings, list items with prices, buttons (with position). */
export function snapshotDom(root) {
  if (!root) return null;
  const rect = root.getBoundingClientRect();
  const where = el => {
    const r = el.getBoundingClientRect();
    const x = (r.left + r.width / 2 - rect.left) / rect.width, y = (r.top + r.height / 2 - rect.top) / rect.height;
    return `${y < 0.34 ? "top" : y > 0.66 ? "bottom" : "middle"} ${x < 0.34 ? "left" : x > 0.66 ? "right" : "centre"}`.replace("middle centre", "centre");
  };
  return {
    title: root.querySelector("[data-screen-title]")?.textContent.trim() || document.title,
    kind: (root.closest("[data-screen-kind]") || root.querySelector("[data-screen-kind]"))?.getAttribute("data-screen-kind") || "page",
    items: [...root.querySelectorAll("[data-screen-item]")].map(el => ({
      name: el.getAttribute("data-name"), qty: +el.getAttribute("data-qty") || 1, price: +el.getAttribute("data-price") || 0, id: el.id,
    })),
    total: +root.querySelector("[data-screen-total]")?.getAttribute("data-screen-total") || null,
    actions: [...root.querySelectorAll("[data-screen-action]")].map(el => ({ label: el.textContent.trim(), id: el.id, where: where(el), primary: el.hasAttribute("data-primary") })),
    private: [...root.querySelectorAll("[data-private]")].length,
  };
}

const inr = n => `₹${n.toLocaleString("en-IN")}`;
const NUM = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
const count = n => (n <= 10 ? NUM[n] : String(n));
const cap = s => s[0].toUpperCase() + s.slice(1);

/**
 * @param {{question: string, intent?: "overview"|"items"|"checkout"|"free", snapshot: any}} req
 * @returns {{answer: string, targets: {id: string, label: string}[], intent: string}}
 */
export function describeLocally({ question = "", intent, snapshot: s }) {
  const q = question.toLowerCase();
  const it = intent || (/checkout|pay|buy/.test(q) ? "checkout" : /item|list|what.*(in|inside)|read/.test(q) ? "items" : "overview");
  const primary = s.actions.find(a => a.primary) || s.actions[0];
  if (it === "items") {
    const parts = s.items.map(i => `${i.qty > 1 ? `${i.qty} × ` : ""}${i.name}, ${inr(i.price * i.qty)}`);
    return { intent: it, answer: `${cap(count(s.items.length))} items. ${parts.join(". ")}.`, targets: s.items.map(i => ({ id: i.id, label: i.name })) };
  }
  if (it === "checkout") {
    if (!primary) return { intent: it, answer: "I can't find a checkout button on this page.", targets: [] };
    return { intent: it, answer: `${primary.label} is at the ${primary.where}. Press it when you're ready. I won't press it for you.`, targets: [{ id: primary.id, label: primary.label }] };
  }
  const total = s.total != null ? `, total ${inr(s.total)}` : "";
  const act = primary ? ` ${primary.label} is a button at the ${primary.where}.` : "";
  return {
    intent: "overview",
    answer: `${cap(s.kind)} page. ${cap(count(s.items.length))} items${total}.${act}`,
    targets: primary ? [{ id: primary.id, label: primary.label }] : [],
  };
}
