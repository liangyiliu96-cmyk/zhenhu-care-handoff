import { createHash } from "node:crypto";
import mammoth from "mammoth";
import { PDFParse } from "pdf-parse";

export const MAX_SOURCE_BYTES = 5 * 1024 * 1024;
export const supportedFormats = new Set(["txt", "md", "pdf", "docx"]);

const expectedMimes = {
  txt: new Set(["text/plain"]),
  md: new Set(["text/markdown", "text/plain"]),
  pdf: new Set(["application/pdf"]),
  docx: new Set(["application/vnd.openxmlformats-officedocument.wordprocessingml.document"])
};

export class DocumentParseError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

function normalizeContent(content) {
  return content.replace(/\r\n/g, "\n").replace(/\r/g, "\n").replace(/[ \t]+\n/g, "\n").trim();
}

function sourceBytes(input) {
  if (typeof input.content === "string") return Buffer.from(input.content, "utf8");
  if (typeof input.fileBase64 !== "string" || !input.fileBase64) throw new DocumentParseError("VALIDATION_ERROR", "缺少知识源文件内容");
  const normalized = input.fileBase64.replace(/\s/g, "");
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(normalized) || normalized.length % 4 !== 0) throw new DocumentParseError("VALIDATION_ERROR", "知识源文件不是合法的 Base64 内容");
  return Buffer.from(normalized, "base64");
}

function validateSource(input, bytes) {
  const format = typeof input.sourceFormat === "string" ? input.sourceFormat.toLowerCase() : "";
  const mime = typeof input.sourceMime === "string" ? input.sourceMime.toLowerCase() : "";
  const name = typeof input.sourceFileName === "string" ? input.sourceFileName.trim() : "";
  if (!supportedFormats.has(format)) throw new DocumentParseError("UNSUPPORTED_DOCUMENT_FORMAT", "PoC 仅支持 .txt、.md、.pdf 和 .docx 文件");
  if (!name || !name.toLowerCase().endsWith(`.${format}`)) throw new DocumentParseError("VALIDATION_ERROR", "来源文件名与声明的文件格式不一致");
  if (!expectedMimes[format].has(mime)) throw new DocumentParseError("UNSUPPORTED_DOCUMENT_MIME", "来源文件 MIME 类型与声明格式不匹配");
  if (!bytes.length || bytes.length > MAX_SOURCE_BYTES) throw new DocumentParseError("SOURCE_FILE_TOO_LARGE", `知识源文件大小必须在 1 字节到 ${MAX_SOURCE_BYTES} 字节之间`);
  if (format === "pdf" && !bytes.subarray(0, 5).equals(Buffer.from("%PDF-"))) throw new DocumentParseError("SOURCE_FILE_SIGNATURE_INVALID", "PDF 文件签名无效");
  if (format === "docx" && !bytes.subarray(0, 4).equals(Buffer.from([0x50, 0x4b, 0x03, 0x04]))) throw new DocumentParseError("SOURCE_FILE_SIGNATURE_INVALID", "DOCX 文件签名无效");
  if ((format === "txt" || format === "md") && bytes.includes(0)) throw new DocumentParseError("SOURCE_FILE_SIGNATURE_INVALID", "文本文件包含二进制空字符");
  return { format, mime, name };
}

async function extractPdfText(bytes) {
  const parser = new PDFParse({ data: bytes });
  try {
    return (await parser.getText()).text;
  } finally {
    await parser.destroy();
  }
}

async function extractDocxText(bytes) {
  const result = await mammoth.extractRawText({ buffer: bytes });
  return result.value;
}

export async function parseKnowledgeSource(input) {
  const bytes = sourceBytes(input);
  const source = validateSource(input, bytes);
  let rawContent;
  try {
    if (source.format === "pdf") rawContent = await extractPdfText(bytes);
    else if (source.format === "docx") rawContent = await extractDocxText(bytes);
    else rawContent = bytes.toString("utf8");
  } catch {
    throw new DocumentParseError("DOCUMENT_PARSE_FAILED", "无法解析该文件；请确认文件未损坏、未加密且格式正确");
  }
  const content = normalizeContent(rawContent);
  if (content.length < 20 || content.length > 60000) throw new DocumentParseError("PARSED_CONTENT_INVALID", "解析后的知识正文长度应在 20 到 60000 个字符之间");
  return {
    content,
    sourceFormat: source.format,
    sourceMime: source.mime,
    sourceFileName: source.name,
    sourceByteLength: bytes.length,
    sourceHash: createHash("sha256").update(bytes).digest("hex")
  };
}
