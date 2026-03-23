import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight } from "lucide-react";
import { MarkdownLine, MarkdownPreview } from "./markdown";
import { cn } from "@/lib/utils";

type HybridMarkdownEditorProps = {
  value: string;
  onChange: (nextValue: string) => void;
  placeholder?: string;
};

type LineBlock = {
  type: "line";
  id: string;
  startLine: number;
  endLine: number;
  markdown: string;
};

type DetailsBlock = {
  type: "details";
  id: string;
  startLine: number;
  endLine: number;
  markdown: string;
  summaryLine: number | null;
  summaryMarkdown: string;
  bodyMarkdown: string;
  defaultOpen: boolean;
};

type RenderBlock = LineBlock | DetailsBlock;

type ActiveEditSpan = {
  startLine: number;
  endLine: number;
  selectionStart: number;
  selectionEnd: number;
};

type PreviewDrag = {
  anchorLine: number;
  currentLine: number;
  selectionStart?: number;
  selectionEnd?: number;
};

function splitLines(value: string): string[] {
  const parts = value.split("\n");
  return parts.length > 0 ? parts : [""];
}

function findDetailsBlockEnd(lines: string[], start: number): number | null {
  for (let index = start + 1; index < lines.length; index += 1) {
    if (lines[index]?.trim().startsWith("</details")) {
      return index;
    }
  }
  return null;
}

function normalizeLineRange(startLine: number, endLine: number) {
  return {
    startLine: Math.min(startLine, endLine),
    endLine: Math.max(startLine, endLine),
  };
}

function lineSpanText(lines: string[], startLine: number, endLine: number): string {
  return lines.slice(startLine, endLine + 1).join("\n");
}

function lineOffsetWithinSpan(lines: string[], spanStartLine: number, targetLine: number, column = 0): number {
  let offset = 0;

  for (let index = spanStartLine; index < targetLine; index += 1) {
    offset += (lines[index] ?? "").length + 1;
  }

  return offset + column;
}

function leadingVisibleContentStart(source: string): number {
  const patterns = [
    /^\s{0,3}#{1,6}\s+/,
    /^\s{0,3}>\s+/,
    /^\s{0,3}(?:[-*+]\s+\[[ xX]\]\s+)/,
    /^\s{0,3}(?:[-*+]\s+)/,
    /^\s{0,3}\d+\.\s+/,
  ];

  for (const pattern of patterns) {
    const match = source.match(pattern);
    if (match) {
      return match[0].length;
    }
  }

  return 0;
}

function textOffsetWithinElement(root: HTMLElement, node: Node, offset: number): number | null {
  if (!root.contains(node)) {
    return null;
  }

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let traversed = 0;
  let current: Node | null = walker.nextNode();

  while (current) {
    const textLength = current.textContent?.length ?? 0;
    if (current === node) {
      return traversed + Math.min(offset, textLength);
    }

    traversed += textLength;
    current = walker.nextNode();
  }

  return traversed;
}

function visibleTextOffsetFromPoint(root: HTMLElement, clientX: number, clientY: number): number | null {
  const documentWithCaret = document as Document & {
    caretPositionFromPoint?: (x: number, y: number) => { offset: number; offsetNode: Node } | null;
    caretRangeFromPoint?: (x: number, y: number) => Range | null;
  };

  const caretPosition = documentWithCaret.caretPositionFromPoint?.(clientX, clientY);
  if (caretPosition) {
    return textOffsetWithinElement(root, caretPosition.offsetNode, caretPosition.offset);
  }

  const caretRange = documentWithCaret.caretRangeFromPoint?.(clientX, clientY);
  if (caretRange) {
    return textOffsetWithinElement(root, caretRange.startContainer, caretRange.startOffset);
  }

  return null;
}

function sourceColumnFromVisibleOffset(source: string, visibleOffset: number): number {
  let rawIndex = leadingVisibleContentStart(source);
  let visibleIndex = 0;

  while (rawIndex < source.length) {
    if (visibleIndex >= visibleOffset) {
      return rawIndex;
    }

    if (source[rawIndex] === "<") {
      const tagEnd = source.indexOf(">", rawIndex);
      if (tagEnd === -1) {
        break;
      }
      rawIndex = tagEnd + 1;
      continue;
    }

    if (source[rawIndex] === "[" && source.indexOf("](", rawIndex) !== -1) {
      const closeBracket = source.indexOf("](", rawIndex);
      const closeParen = closeBracket !== -1 ? source.indexOf(")", closeBracket + 2) : -1;

      if (closeBracket !== -1 && closeParen !== -1) {
        const linkTextLength = closeBracket - rawIndex - 1;
        if (visibleIndex + linkTextLength >= visibleOffset) {
          return rawIndex + 1 + Math.max(0, visibleOffset - visibleIndex);
        }
        visibleIndex += linkTextLength;
        rawIndex = closeParen + 1;
        continue;
      }
    }

    if ("*_~`".includes(source[rawIndex] ?? "")) {
      rawIndex += 1;
      continue;
    }

    if ("[]()".includes(source[rawIndex] ?? "")) {
      rawIndex += 1;
      continue;
    }

    visibleIndex += 1;
    rawIndex += 1;
  }

  return Math.min(rawIndex, source.length);
}

function selectionForPreviewLine(line: string, root: HTMLElement, clientX: number, clientY: number): { start: number; end: number } {
  const visibleOffset = visibleTextOffsetFromPoint(root, clientX, clientY);
  if (visibleOffset === null) {
    return {
      start: line.length,
      end: line.length,
    };
  }

  const sourceColumn = sourceColumnFromVisibleOffset(line, visibleOffset);
  return {
    start: sourceColumn,
    end: sourceColumn,
  };
}

function summaryCaretColumn(line: string): number {
  const match = line.match(/<summary\b[^>]*>/i);
  if (!match) {
    return 0;
  }
  return Math.min(line.length, (match.index ?? 0) + match[0].length);
}

function rangeIntersects(block: RenderBlock, startLine: number, endLine: number): boolean {
  return block.endLine >= startLine && block.startLine <= endLine;
}

function expandRangeToBlockBoundaries(blocks: RenderBlock[], startLine: number, endLine: number) {
  let next = normalizeLineRange(startLine, endLine);
  let changed = true;

  while (changed) {
    changed = false;

    for (const block of blocks) {
      if (!rangeIntersects(block, next.startLine, next.endLine)) {
        continue;
      }

      if (block.type === "details" && (block.startLine < next.startLine || block.endLine > next.endLine)) {
        next = {
          startLine: Math.min(next.startLine, block.startLine),
          endLine: Math.max(next.endLine, block.endLine),
        };
        changed = true;
      }
    }
  }

  return next;
}

function parseDetailsBlock(lines: string[], startLine: number, endLine: number): DetailsBlock {
  const markdown = lineSpanText(lines, startLine, endLine);
  const blockLines = lines.slice(startLine, endLine + 1);
  const openTag = blockLines[0] ?? "";
  const defaultOpen = /\bopen\b/i.test(openTag);

  let summaryLine: number | null = null;
  let summaryMarkdown = "Details";

  for (let index = 0; index < blockLines.length; index += 1) {
    const line = blockLines[index] ?? "";
    if (!line.includes("<summary")) {
      continue;
    }

    summaryLine = startLine + index;
    summaryMarkdown = line
      .replace(/^.*?<summary\b[^>]*>/i, "")
      .replace(/<\/summary>.*$/i, "")
      .trim();
    break;
  }

  const bodyStartLine = summaryLine === null ? startLine + 1 : summaryLine + 1;
  const bodyLines = lines.slice(bodyStartLine, endLine);

  return {
    type: "details",
    id: `details-${startLine}-${endLine}`,
    startLine,
    endLine,
    markdown,
    summaryLine,
    summaryMarkdown,
    bodyMarkdown: bodyLines.join("\n"),
    defaultOpen,
  };
}

function buildRenderBlocks(lines: string[]): RenderBlock[] {
  const blocks: RenderBlock[] = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    const trimmed = line.trim();

    if (trimmed.startsWith("<details")) {
      const endLine = findDetailsBlockEnd(lines, index);
      if (endLine !== null) {
        blocks.push(parseDetailsBlock(lines, index, endLine));
        index = endLine;
        continue;
      }
    }

    blocks.push({
      type: "line",
      id: `line-${index}`,
      startLine: index,
      endLine: index,
      markdown: line,
    });
  }

  return blocks;
}

function shouldLetPreviewInteractionPass(event: MouseEvent | React.MouseEvent<HTMLElement>): boolean {
  if (!(event.target instanceof HTMLElement)) {
    return false;
  }

  if (event.target.closest("[data-editor-preview-control='true']")) {
    return true;
  }

  if (event.target.closest("a")) {
    return event.metaKey || event.ctrlKey;
  }

  return false;
}

function DetailsPreviewBlock({
  block,
  open,
  selected,
  onBodyMouseDown,
  onBodyMouseEnter,
  onPreviewClickCapture,
  onToggleOpen,
}: {
  block: DetailsBlock;
  open: boolean;
  selected: boolean;
  onBodyMouseDown: (event: React.MouseEvent<HTMLDivElement>) => void;
  onBodyMouseEnter: () => void;
  onPreviewClickCapture: (event: React.MouseEvent<HTMLDivElement>) => void;
  onToggleOpen: () => void;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-stone-800/90 bg-stone-950/60 px-4 py-3 transition-colors",
        selected && "border-amber-300/40 bg-stone-900/85",
      )}
      onMouseDown={onBodyMouseDown}
      onMouseEnter={onBodyMouseEnter}
      onClickCapture={onPreviewClickCapture}
    >
      <div className="flex items-start gap-3">
        <button
          type="button"
          data-editor-preview-control="true"
          className="mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-lg text-stone-500 transition-colors hover:bg-stone-900 hover:text-stone-200"
          onMouseDown={(event) => {
            event.preventDefault();
            event.stopPropagation();
          }}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onToggleOpen();
          }}
          aria-label={open ? "Collapse details" : "Expand details"}
        >
          <ChevronRight className={cn("size-4 transition-transform duration-150", open && "rotate-90 text-amber-200")} />
        </button>

        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-stone-100">
            <MarkdownLine markdown={block.summaryMarkdown || "Details"} placeholder="Details" />
          </div>

          {open && block.bodyMarkdown.trim() ? (
            <div className="mt-3 border-t border-stone-800/80 pt-3">
              <MarkdownPreview markdown={block.bodyMarkdown} />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function HybridMarkdownEditor({
  value,
  onChange,
  placeholder = "# Start writing...",
}: HybridMarkdownEditorProps) {
  const [activeEditSpan, setActiveEditSpan] = useState<ActiveEditSpan | null>(null);
  const [previewDrag, setPreviewDrag] = useState<PreviewDrag | null>(null);
  const [openDetailsBlocks, setOpenDetailsBlocks] = useState<Record<string, boolean>>({});
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const lines = splitLines(value);
  const blocks = useMemo(() => buildRenderBlocks(lines), [lines]);
  const isDocumentEmpty = value.trim().length === 0;

  const previewSelectionRange = previewDrag
    ? expandRangeToBlockBoundaries(blocks, previewDrag.anchorLine, previewDrag.currentLine)
    : null;

  useEffect(() => {
    if (!activeEditSpan) {
      return;
    }

    const maxLine = Math.max(0, lines.length - 1);
    const nextStartLine = Math.min(activeEditSpan.startLine, maxLine);
    const nextEndLine = Math.min(activeEditSpan.endLine, maxLine);

    if (nextStartLine === activeEditSpan.startLine && nextEndLine === activeEditSpan.endLine) {
      return;
    }

    const nextValue = lineSpanText(lines, nextStartLine, nextEndLine);
    setActiveEditSpan({
      startLine: nextStartLine,
      endLine: nextEndLine,
      selectionStart: Math.min(activeEditSpan.selectionStart, nextValue.length),
      selectionEnd: Math.min(activeEditSpan.selectionEnd, nextValue.length),
    });
  }, [activeEditSpan, lines]);

  useEffect(() => {
    const input = inputRef.current;
    if (!input || !activeEditSpan) {
      return;
    }

    input.style.height = "0px";
    input.style.height = `${Math.max(44, input.scrollHeight)}px`;
    input.focus();

    const start = Math.min(activeEditSpan.selectionStart, input.value.length);
    const end = Math.min(activeEditSpan.selectionEnd, input.value.length);
    input.setSelectionRange(start, end);
  }, [activeEditSpan, value]);

  useEffect(() => {
    if (!previewDrag) {
      return;
    }

    const { anchorLine, currentLine, selectionStart, selectionEnd } = previewDrag;

    function handleWindowMouseUp() {
      const rawRange = normalizeLineRange(anchorLine, currentLine);
      const expandedRange = expandRangeToBlockBoundaries(blocks, anchorLine, currentLine);
      activateEditSpan(expandedRange.startLine, expandedRange.endLine, {
        selectAll: rawRange.startLine !== rawRange.endLine,
        selectionStart,
        selectionEnd,
      });
      setPreviewDrag(null);
    }

    window.addEventListener("mouseup", handleWindowMouseUp);

    return () => {
      window.removeEventListener("mouseup", handleWindowMouseUp);
    };
  }, [blocks, previewDrag, value]);

  function updateActiveSpan(nextText: string, selectionStart: number, selectionEnd: number) {
    if (!activeEditSpan) {
      return;
    }

    const nextParts = splitLines(nextText);
    const nextLines = [...lines];
    nextLines.splice(activeEditSpan.startLine, activeEditSpan.endLine - activeEditSpan.startLine + 1, ...nextParts);
    onChange(nextLines.join("\n"));
    setActiveEditSpan({
      startLine: activeEditSpan.startLine,
      endLine: activeEditSpan.startLine + nextParts.length - 1,
      selectionStart,
      selectionEnd,
    });
  }

  function defaultSelectionForRange(startLine: number, endLine: number): { selectionStart: number; selectionEnd: number } {
    if (startLine !== endLine) {
      const selectedText = lineSpanText(lines, startLine, endLine);
      return {
        selectionStart: 0,
        selectionEnd: selectedText.length,
      };
    }

    const block = blocks.find((item) => item.startLine <= startLine && item.endLine >= endLine);
    if (block?.type === "details") {
      const summaryLine = block.summaryLine ?? block.startLine;
      const column = summaryLine === block.summaryLine ? summaryCaretColumn(lines[summaryLine] ?? "") : 0;
      const offset = lineOffsetWithinSpan(lines, block.startLine, summaryLine, column);
      return { selectionStart: offset, selectionEnd: offset };
    }

    const lineLength = (lines[endLine] ?? "").length;
    return { selectionStart: lineLength, selectionEnd: lineLength };
  }

  function activateEditSpan(
    startLine: number,
    endLine: number,
    options?: {
      selectAll?: boolean;
      selectionStart?: number;
      selectionEnd?: number;
    },
  ) {
    const expandedRange = expandRangeToBlockBoundaries(blocks, startLine, endLine);
    const spanText = lineSpanText(lines, expandedRange.startLine, expandedRange.endLine);
    const fallbackSelection = defaultSelectionForRange(expandedRange.startLine, expandedRange.endLine);

    setActiveEditSpan({
      startLine: expandedRange.startLine,
      endLine: expandedRange.endLine,
      selectionStart: options?.selectAll ? 0 : Math.min(options?.selectionStart ?? fallbackSelection.selectionStart, spanText.length),
      selectionEnd: options?.selectAll ? spanText.length : Math.min(options?.selectionEnd ?? fallbackSelection.selectionEnd, spanText.length),
    });
  }

  function handlePreviewMouseDown(
    event: React.MouseEvent<HTMLDivElement>,
    block: RenderBlock,
    lineHint = block.startLine,
  ) {
    if (event.button !== 0 || shouldLetPreviewInteractionPass(event)) {
      return;
    }

    event.preventDefault();
    const anchorLine = block.type === "details" ? block.startLine : lineHint;
    const nextSelection =
      block.type === "line"
        ? selectionForPreviewLine(block.markdown, event.currentTarget, event.clientX, event.clientY)
        : undefined;

    setPreviewDrag({
      anchorLine,
      currentLine: anchorLine,
      selectionStart: nextSelection?.start,
      selectionEnd: nextSelection?.end,
    });
  }

  function handlePreviewClickCapture(event: React.MouseEvent<HTMLDivElement>) {
    if (shouldLetPreviewInteractionPass(event)) {
      return;
    }

    if (event.target instanceof HTMLElement && event.target.closest("a")) {
      event.preventDefault();
    }
  }

  function updatePreviewDrag(nextLine: number) {
    setPreviewDrag((current) => (current ? { ...current, currentLine: nextLine } : current));
  }

  const activeText = activeEditSpan ? lineSpanText(lines, activeEditSpan.startLine, activeEditSpan.endLine) : "";

  return (
    <div
      className="min-h-[60vh] cursor-text px-1 py-2"
      onMouseDown={(event) => {
        if (event.target !== event.currentTarget) {
          return;
        }

        event.preventDefault();
        activateEditSpan(Math.max(0, lines.length - 1), Math.max(0, lines.length - 1));
      }}
    >
      {blocks.map((block) => {
        const isBeforeActive = activeEditSpan ? block.endLine < activeEditSpan.startLine : true;
        const isAfterActive = activeEditSpan ? block.startLine > activeEditSpan.endLine : true;
        const isInsideActive = activeEditSpan ? rangeIntersects(block, activeEditSpan.startLine, activeEditSpan.endLine) : false;
        const isPreviewSelected = previewSelectionRange
          ? rangeIntersects(block, previewSelectionRange.startLine, previewSelectionRange.endLine)
          : false;

        if (activeEditSpan && isInsideActive && block.startLine === activeEditSpan.startLine) {
          return (
            <div key={`editor-${activeEditSpan.startLine}-${activeEditSpan.endLine}`} className="px-3 py-0.5">
              <textarea
                ref={inputRef}
                rows={Math.max(activeEditSpan.endLine - activeEditSpan.startLine + 1, 1)}
                className="block min-h-[1.75rem] w-full resize-none border-0 bg-transparent p-0 text-[15px] leading-7 text-stone-100 outline-none placeholder:text-stone-500"
                value={activeText}
                spellCheck={false}
                placeholder={placeholder}
                onBlur={() => {
                  setActiveEditSpan(null);
                }}
                onSelect={(event) => {
                  const { selectionStart, selectionEnd } = event.currentTarget;
                  setActiveEditSpan((current) =>
                    current
                      ? {
                          ...current,
                          selectionStart,
                          selectionEnd,
                        }
                      : current,
                  );
                }}
                onChange={(event) => {
                  const { value: nextValue, selectionStart, selectionEnd } = event.currentTarget;
                  updateActiveSpan(nextValue, selectionStart, selectionEnd);
                }}
                onKeyDown={(event) => {
                  const { selectionStart, selectionEnd, value: currentValue } = event.currentTarget;

                  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "a") {
                    event.preventDefault();
                    setActiveEditSpan({
                      startLine: 0,
                      endLine: Math.max(0, lines.length - 1),
                      selectionStart: 0,
                      selectionEnd: value.length,
                    });
                    return;
                  }

                  if (event.key === "Tab") {
                    event.preventDefault();
                    const nextValue = `${currentValue.slice(0, selectionStart)}  ${currentValue.slice(selectionEnd)}`;
                    const nextSelection = selectionStart + 2;
                    updateActiveSpan(nextValue, nextSelection, nextSelection);
                    return;
                  }

                  if (
                    event.key === "ArrowUp" &&
                    selectionStart === selectionEnd &&
                    selectionStart === 0 &&
                    activeEditSpan.startLine > 0
                  ) {
                    event.preventDefault();
                    activateEditSpan(activeEditSpan.startLine - 1, activeEditSpan.startLine - 1);
                    return;
                  }

                  if (
                    event.key === "ArrowDown" &&
                    selectionStart === selectionEnd &&
                    selectionEnd === currentValue.length &&
                    activeEditSpan.endLine < lines.length - 1
                  ) {
                    event.preventDefault();
                    activateEditSpan(activeEditSpan.endLine + 1, activeEditSpan.endLine + 1, {
                      selectionStart: 0,
                      selectionEnd: 0,
                    });
                  }
                }}
              />
            </div>
          );
        }

        if (activeEditSpan && !isBeforeActive && !isAfterActive) {
          return null;
        }

        if (block.type === "details") {
          const open = openDetailsBlocks[block.id] ?? block.defaultOpen;

          return (
            <div key={block.id} className="px-3 py-1">
              <DetailsPreviewBlock
                block={block}
                open={open}
                selected={isPreviewSelected}
                onBodyMouseDown={(event) => handlePreviewMouseDown(event, block)}
                onBodyMouseEnter={() => updatePreviewDrag(block.endLine)}
                onPreviewClickCapture={handlePreviewClickCapture}
                onToggleOpen={() => {
                  setOpenDetailsBlocks((current) => ({
                    ...current,
                    [block.id]: !open,
                  }));
                }}
              />
            </div>
          );
        }

        const showEmptyPlaceholder = isDocumentEmpty && block.startLine === 0 && !activeEditSpan;
        const isBlank = block.markdown.trim().length === 0;

        return (
          <div
            key={block.id}
            className={cn(
              "min-h-7 px-3 py-0.5 text-[15px] leading-7 transition-colors duration-100",
              isPreviewSelected && "rounded-lg bg-stone-900/85",
            )}
            onMouseDown={(event) => handlePreviewMouseDown(event, block, block.startLine)}
            onMouseEnter={() => updatePreviewDrag(block.startLine)}
            onClickCapture={handlePreviewClickCapture}
          >
            {showEmptyPlaceholder ? (
              <span className="text-sm text-stone-500/80">{placeholder}</span>
            ) : isBlank ? (
              <span className="block min-h-[1.75rem]">&nbsp;</span>
            ) : (
              <MarkdownLine markdown={block.markdown} />
            )}
          </div>
        );
      })}
    </div>
  );
}
