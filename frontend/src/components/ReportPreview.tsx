import type { ReactNode } from "react";

type Block =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "quote"; text: string }
  | { type: "code"; text: string }
  | { type: "rule" };

export function ReportPreview({ markdown }: { markdown: string }) {
  if (!markdown.trim()) {
    return (
      <div className="report-preview empty-preview">
        <p>从左侧选择一份报告，正文和证据会在这里展开。</p>
      </div>
    );
  }

  const blocks = parseBlocks(markdown);
  if (blocks[0]?.type === "heading" && blocks[0].level === 1) blocks.shift();
  return (
    <article className="report-preview report-document">
      {blocks.map((block, index) => renderBlock(block, index))}
    </article>
  );
}

function parseBlocks(markdown: string): Block[] {
  const lines = markdown.replaceAll("\r\n", "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let code: string[] | null = null;

  function flushParagraph() {
    if (paragraph.length) blocks.push({ type: "paragraph", text: paragraph.join(" ") });
    paragraph = [];
  }

  function flushList() {
    if (list) blocks.push({ type: "list", ...list });
    list = null;
  }

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      flushParagraph();
      flushList();
      if (code) {
        blocks.push({ type: "code", text: code.join("\n") });
        code = null;
      } else {
        code = [];
      }
      continue;
    }
    if (code) {
      code.push(line);
      continue;
    }
    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    const unordered = /^\s*[-*]\s+(.+)$/.exec(line);
    const ordered = /^\s*\d+[.)]\s+(.+)$/.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
    } else if (unordered || ordered) {
      flushParagraph();
      const nextOrdered = Boolean(ordered);
      if (!list || list.ordered !== nextOrdered) flushList();
      list ||= { ordered: nextOrdered, items: [] };
      list.items.push((ordered || unordered)![1]);
    } else if (/^\s*>\s?/.test(line)) {
      flushParagraph();
      flushList();
      blocks.push({ type: "quote", text: line.replace(/^\s*>\s?/, "") });
    } else if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      flushParagraph();
      flushList();
      blocks.push({ type: "rule" });
    } else if (!line.trim()) {
      flushParagraph();
      flushList();
    } else {
      flushList();
      paragraph.push(line.trim());
    }
  }
  flushParagraph();
  flushList();
  if (code) blocks.push({ type: "code", text: code.join("\n") });
  return blocks;
}

function renderBlock(block: Block, key: number): ReactNode {
  if (block.type === "heading") {
    if (block.level === 1) return <h1 key={key}>{inline(block.text)}</h1>;
    if (block.level === 2) return <h2 key={key}>{inline(block.text)}</h2>;
    return <h3 key={key}>{inline(block.text)}</h3>;
  }
  if (block.type === "paragraph") return <p key={key}>{inline(block.text)}</p>;
  if (block.type === "quote") return <blockquote key={key}>{inline(block.text)}</blockquote>;
  if (block.type === "code") return <pre key={key}><code>{block.text}</code></pre>;
  if (block.type === "rule") return <hr key={key} />;
  const Tag = block.ordered ? "ol" : "ul";
  return <Tag key={key}>{block.items.map((item, index) => <li key={index}>{inline(item)}</li>)}</Tag>;
}

function inline(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    return part;
  });
}
