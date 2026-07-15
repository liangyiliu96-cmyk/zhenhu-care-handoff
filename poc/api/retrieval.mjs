function termsOf(input) {
  const text = input.toLowerCase().replace(/\s+/g, "");
  const terms = [];
  for (let index = 0; index < text.length; index += 1) {
    terms.push(text[index]);
    if (index < text.length - 1) terms.push(text.slice(index, index + 2));
  }
  return terms.filter((term) => /[\p{L}\p{N}]/u.test(term));
}

function frequencies(terms) {
  const counts = new Map();
  for (const term of terms) counts.set(term, (counts.get(term) ?? 0) + 1);
  return counts;
}

function cosine(left, right) {
  let dot = 0;
  let leftNorm = 0;
  let rightNorm = 0;
  for (const value of left.values()) leftNorm += value ** 2;
  for (const value of right.values()) rightNorm += value ** 2;
  for (const [term, value] of left) dot += value * (right.get(term) ?? 0);
  return leftNorm && rightNorm ? dot / Math.sqrt(leftNorm * rightNorm) : 0;
}

export class LocalTfidfIndex {
  constructor(documents) {
    this.entries = documents.flatMap((document) => document.chunks.map((chunk) => ({ document, chunk, terms: termsOf(`${document.title} ${chunk.location} ${chunk.text}`) })));
    this.documentFrequency = new Map();
    for (const entry of this.entries) {
      for (const term of new Set(entry.terms)) this.documentFrequency.set(term, (this.documentFrequency.get(term) ?? 0) + 1);
    }
  }

  vector(terms) {
    const frequency = frequencies(terms);
    const total = this.entries.length || 1;
    return new Map([...frequency].map(([term, count]) => [term, count * Math.log((total + 1) / ((this.documentFrequency.get(term) ?? 0) + 1) + 1)]));
  }

  search(query) {
    const queryTerms = termsOf(query);
    const queryVector = this.vector(queryTerms);
    return this.entries.map((entry) => {
      const entryVector = this.vector(entry.terms);
      const cosineScore = cosine(queryVector, entryVector);
      const lexicalHits = queryTerms.filter((term) => entry.terms.includes(term)).length;
      const lexicalScore = queryTerms.length ? lexicalHits / queryTerms.length : 0;
      return { document: entry.document, chunk: entry.chunk, cosineScore, lexicalScore, score: Number((cosineScore * 0.7 + lexicalScore * 0.3).toFixed(4)) };
    }).filter((result) => result.score > 0).sort((left, right) => right.score - left.score);
  }
}
