import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Source } from "./api";

function inline(text: string, sources: Source[]): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[\w-]+(?:#[^\]]+)?\])/g).map((piece, index) => {
    if (piece.startsWith("**") && piece.endsWith("**")) return <strong key={index}>{piece.slice(2, -2)}</strong>;
    if (piece.startsWith("`") && piece.endsWith("`")) return <code key={index}>{piece.slice(1, -1)}</code>;
    const citation = /^\[([\w-]+)(?:#([^\]]+))?\]$/.exec(piece);
    const source = citation && sources.find(s => s.id === citation[1]);
    if (source && citation && (!citation[2] || source.sections?.includes(citation[2]))) {
      return <Link className="inline-source" key={index} to={`/knowledge/${source.id}${citation[2] ? "#" + encodeURIComponent(citation[2]) : ""}`}>〔{source.title}{citation[2] ? " · " + citation[2] : ""}〕</Link>;
    }
    return piece;
  });
}

/** Deliberately small Markdown subset. React escapes HTML; no raw HTML or remote links. */
export function AnswerContent({ text, sources = [] }: { text: string; sources?: Source[] }) {
  const lines = text.split("\n"), blocks: ReactNode[] = [];
  let index = 0;
  const tableCells = (row: string) => row.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index++; continue; }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      const key = index++, content = inline(heading[2], sources);
      blocks.push(heading[1].length <= 2 ? <h3 key={key}>{content}</h3> : <h4 key={key}>{content}</h4>);
    } else if (line.includes("|") && /^\s*\|?[\s:|\-]+\|?\s*$/.test(lines[index + 1] || "")) {
      const key = index, headers = tableCells(line), rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|")) rows.push(tableCells(lines[index++]));
      blocks.push(<div className="answer-table" role="region" aria-label="回答中的比较表" tabIndex={0} key={key}><table><thead><tr>{headers.map((h, i) => <th scope="col" key={i}>{inline(h, sources)}</th>)}</tr></thead><tbody>{rows.map((row, r) => <tr key={r}>{headers.map((_, c) => <td key={c}>{inline(row[c] || "", sources)}</td>)}</tr>)}</tbody></table></div>);
    } else if (/^\s*(?:[-*] |\d+\. )/.test(line)) {
      const key = index, ordered = /^\s*\d+\. /.test(line), items: string[] = [];
      while (index < lines.length && (ordered ? /^\s*\d+\. / : /^\s*[-*] /).test(lines[index])) items.push(lines[index++].replace(/^\s*(?:[-*] |\d+\. )/, ""));
      const content = items.map((item, i) => <li key={i}>{inline(item, sources)}</li>);
      blocks.push(ordered ? <ol key={key}>{content}</ol> : <ul key={key}>{content}</ul>);
    } else {
      const key = index, paragraphs = [lines[index++]];
      while (index < lines.length && lines[index].trim() && !/^(#{1,3}\s|[-*] |\d+\. |\|)/.test(lines[index])) paragraphs.push(lines[index++]);
      blocks.push(<p key={key}>{inline(paragraphs.join("\n"), sources)}</p>);
    }
  }
  return <div className="answer-content">{blocks}</div>;
}
