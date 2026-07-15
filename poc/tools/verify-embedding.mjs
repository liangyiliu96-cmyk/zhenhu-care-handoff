import { KnowledgeRegistry } from "../api/knowledge.mjs";

const knowledge = new KnowledgeRegistry({ enableSemantic: true });
const results = await knowledge.search("doctor", "青霉素过敏");
const first = results[0];
if (!first || first.retrievalStrategyVersion !== "poc-multilingual-embedding-hybrid-rag-0.1") {
  throw new Error(`Embedding verification failed: ${first?.retrievalStrategyVersion ?? "no result"}`);
}
console.log(JSON.stringify({ documentId: first.documentId, score: first.score, strategy: first.retrievalStrategyVersion, retrieval: first.retrieval, health: knowledge.health() }, null, 2));
