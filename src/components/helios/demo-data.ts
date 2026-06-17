export const TRACES = [
  { id: "trc_8f2a31e", app: "agent.research_assistant", query: "What changed in the Q3 revenue policy?", model: "gpt-4o", lat: 1420, cost: 0.018, tok: 2341, status: "success" as const, ago: "12s" },
  { id: "trc_7c1f902", app: "agent.support_router", query: "How do I rotate API keys without downtime?", model: "gpt-4o", lat: 980, cost: 0.011, tok: 1842, status: "success" as const, ago: "31s" },
  { id: "trc_4a90b21", app: "rag.knowledge_base", query: "Is there a SOC2 type II report available?", model: "claude-3.5", lat: 1810, cost: 0.014, tok: 2003, status: "warn" as const, ago: "1m" },
  { id: "trc_ee21d04", app: "agent.research_assistant", query: "Summarize the changelog for v1.2.", model: "gpt-4o", lat: 612, cost: 0.006, tok: 1102, status: "success" as const, ago: "2m" },
  { id: "trc_91b2c77", app: "agent.support_router", query: "Can I export traces to datadog?", model: "gemini-1.5", lat: 2410, cost: 0.009, tok: 1980, status: "error" as const, ago: "3m" },
  { id: "trc_2c0a18e", app: "rag.knowledge_base", query: "Refund window for annual plans?", model: "gpt-4o", lat: 1320, cost: 0.012, tok: 1721, status: "success" as const, ago: "4m" },
  { id: "trc_6b81a02", app: "agent.research_assistant", query: "Diff between prompt v2 and v3.", model: "claude-3.5", lat: 1502, cost: 0.013, tok: 1888, status: "success" as const, ago: "6m" },
  { id: "trc_3f9c211", app: "agent.support_router", query: "Why am I getting 429 on the eval API?", model: "gpt-4o", lat: 720, cost: 0.005, tok: 932, status: "error" as const, ago: "8m" },
];

export const PROMPTS = [
  { name: "support.router.system", versions: 6, latest: "v6", model: "gpt-4o", score: 88.1, lat: "1.51s", cost: "$0.020", updated: "2d ago" },
  { name: "research.summarizer", versions: 4, latest: "v4", model: "claude-3.5", score: 91.4, lat: "1.78s", cost: "$0.015", updated: "5h ago" },
  { name: "rag.answer.synth", versions: 9, latest: "v9", model: "gpt-4o", score: 84.7, lat: "1.32s", cost: "$0.012", updated: "1d ago" },
  { name: "router.classify.intent", versions: 3, latest: "v3", model: "gpt-4o-mini", score: 76.2, lat: "0.41s", cost: "$0.001", updated: "1w ago" },
];

export const DATASETS = [
  { name: "support_qa.v4", examples: 412, owner: "mm@helios.dev", updated: "yesterday" },
  { name: "research_summaries.v2", examples: 218, owner: "kr@helios.dev", updated: "3d ago" },
  { name: "policy_retrieval.v1", examples: 96, owner: "ai-team", updated: "1w ago" },
];

export function statusTone(s: "success" | "warn" | "error"): "success" | "warn" | "danger" {
  return s === "success" ? "success" : s === "warn" ? "warn" : "danger";
}