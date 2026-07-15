import { env, pipeline } from "@huggingface/transformers";
import { resolve } from "node:path";

export const EMBEDDING_MODEL = process.env.POC_EMBEDDING_MODEL ?? "Xenova/paraphrase-multilingual-MiniLM-L12-v2";
env.cacheDir = resolve(process.cwd(), "poc", ".cache", "huggingface");

let extractorPromise;

async function extractor() {
  extractorPromise ??= pipeline("feature-extraction", EMBEDDING_MODEL, { dtype: "q8" });
  return extractorPromise;
}

function cosine(left, right) {
  let dot = 0;
  let leftNorm = 0;
  let rightNorm = 0;
  for (let index = 0; index < left.length; index += 1) {
    dot += left[index] * right[index];
    leftNorm += left[index] ** 2;
    rightNorm += right[index] ** 2;
  }
  return leftNorm && rightNorm ? dot / Math.sqrt(leftNorm * rightNorm) : 0;
}

export class MultilingualEmbeddingIndex {
  constructor(documents) {
    this.entries = documents.flatMap((document) => document.chunks.map((chunk) => ({ document, chunk, text: `${document.title} ${chunk.location} ${chunk.text}` })));
    this.vectors = null;
    this.state = "idle";
    this.dimension = null;
    this.lastError = null;
  }

  async embed(texts) {
    const model = await extractor();
    const output = await model(texts, { pooling: "mean", normalize: true });
    return output.tolist();
  }

  async build() {
    if (this.vectors) return;
    this.state = "loading";
    try {
      this.vectors = await this.embed(this.entries.map((entry) => entry.text));
      this.dimension = this.vectors[0]?.length ?? 0;
      this.state = "ready";
    } catch (error) {
      this.state = "failed";
      this.lastError = error instanceof Error ? error.message : String(error);
      throw error;
    }
  }

  async search(query) {
    await this.build();
    const [queryVector] = await this.embed([query]);
    return this.entries.map((entry, index) => ({ ...entry, score: Number(cosine(queryVector, this.vectors[index]).toFixed(4)) })).sort((left, right) => right.score - left.score);
  }

  status() {
    return { state: this.state, model: EMBEDDING_MODEL, dimension: this.dimension, error: this.lastError };
  }
}
