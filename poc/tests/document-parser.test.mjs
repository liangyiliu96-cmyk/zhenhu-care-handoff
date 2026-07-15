import assert from "node:assert/strict";
import test from "node:test";
import JSZip from "jszip";
import { DocumentParseError, parseKnowledgeSource } from "../api/document-parser.mjs";

function sourceInput(overrides = {}) {
  return {
    sourceFileName: "fixture.txt",
    sourceFormat: "txt",
    sourceMime: "text/plain",
    content: "这是满足最小长度要求的模拟文本知识内容，用于验证受控文档解析。",
    ...overrides
  };
}

function minimalPdf(text) {
  const escaped = text.replace(/([\\()])/g, "\\$1");
  const stream = `BT\n/F1 16 Tf\n72 720 Td\n(${escaped}) Tj\nET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xrefOffset = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  pdf += offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("");
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;
  return Buffer.from(pdf, "utf8");
}

async function minimalDocx(text) {
  const zip = new JSZip();
  zip.file("[Content_Types].xml", `<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>`);
  zip.folder("_rels").file(".rels", `<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>`);
  zip.folder("word").file("document.xml", `<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>${text}</w:t></w:r></w:p><w:sectPr/></w:body></w:document>`);
  return zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
}

test("文本来源经过 MIME、大小与内容哈希处理", async () => {
  const parsed = await parseKnowledgeSource(sourceInput());
  assert.equal(parsed.sourceFormat, "txt");
  assert.equal(parsed.sourceMime, "text/plain");
  assert.equal(parsed.sourceByteLength, Buffer.byteLength(sourceInput().content));
  assert.match(parsed.sourceHash, /^[a-f0-9]{64}$/);
});

test("PDF 来源通过签名校验并提取正文", async () => {
  const bytes = minimalPdf("PDF parser fixture text");
  const parsed = await parseKnowledgeSource(sourceInput({
    sourceFileName: "fixture.pdf",
    sourceFormat: "pdf",
    sourceMime: "application/pdf",
    fileBase64: bytes.toString("base64"),
    content: undefined
  }));
  assert.match(parsed.content, /PDF parser fixture text/);
  assert.equal(parsed.sourceByteLength, bytes.length);
});

test("DOCX 来源通过压缩包签名校验并提取正文", async () => {
  const bytes = await minimalDocx("DOCX parser fixture text");
  const parsed = await parseKnowledgeSource(sourceInput({
    sourceFileName: "fixture.docx",
    sourceFormat: "docx",
    sourceMime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    fileBase64: bytes.toString("base64"),
    content: undefined
  }));
  assert.match(parsed.content, /DOCX parser fixture text/);
  assert.equal(parsed.sourceByteLength, bytes.length);
});

test("格式、MIME 与签名错误被明确拒绝", async () => {
  await assert.rejects(parseKnowledgeSource(sourceInput({ sourceMime: "application/pdf" })), (error) => error instanceof DocumentParseError && error.code === "UNSUPPORTED_DOCUMENT_MIME");
  await assert.rejects(parseKnowledgeSource(sourceInput({
    sourceFileName: "not-a-pdf.pdf", sourceFormat: "pdf", sourceMime: "application/pdf", fileBase64: Buffer.from("not a PDF").toString("base64"), content: undefined
  })), (error) => error instanceof DocumentParseError && error.code === "SOURCE_FILE_SIGNATURE_INVALID");
});
